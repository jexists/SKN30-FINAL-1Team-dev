import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import case, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import contract_management, report_writing, schedule_management
from app.core.config import settings
from app.db.session import get_sessionmaker
from app.ml.deal_baseline import DealModelError
from app.models.agent import AgentRun
from app.models.content import Report
from app.models.workspace import Member
from app.schemas.agent_runs import (
    AgentRunCreate,
    AgentRunRead,
    ReportGenerationCreate,
    ReportGenerationInput,
    ReportGenerationScope,
)
from app.services import contract_schedule_snapshots, meeting_processing, report_sources
from app.services.llm import LLMError, is_transient_llm_error

_SEOUL = ZoneInfo("Asia/Seoul")
REPORT_GENERATION_RETENTION = timedelta(hours=24)
REPORT_GENERATION_CODES = ("meeting_processing", "report_writing")


def _seoul(value: datetime | None) -> datetime | None:
    """DB 에는 UTC 로 두고 응답에서만 서울 시간으로 바꾼다."""
    return None if value is None else value.astimezone(_SEOUL)


def generation_payload_visible(run: AgentRun | AgentRunRead, requester_id: UUID) -> bool:
    """보고서 원문·초안은 생성 요청자에게 보존 기한 동안만 공개한다."""
    if run.agent_code not in REPORT_GENERATION_CODES:
        return True
    if run.requested_by_member_id != requester_id or run.payload_redacted_at is not None:
        return False
    return run.payload_expires_at is not None and run.payload_expires_at > datetime.now(UTC)


def _generation_input_read(run: AgentRun, requester_id: UUID) -> ReportGenerationInput | None:
    """Return only the requester's UI input; never expose the frozen CRM snapshot."""
    if (
        not generation_payload_visible(run, requester_id)
        or run.agent_code not in REPORT_GENERATION_CODES
        or run.scope_key is None
        or run.payload_expires_at is None
        or not run.request_snapshot
    ):
        return None
    return ReportGenerationInput.model_validate(run.request_snapshot)


def _output_read(run: AgentRun, requester_id: UUID) -> dict[str, Any] | None:
    if not generation_payload_visible(run, requester_id):
        return None
    output = run.output_snapshot
    if run.agent_code != "meeting_processing" or not isinstance(output, dict):
        return output
    # context_lookups contains frozen CRM fragments used internally for grounding.
    return {
        key: value
        for key, value in output.items()
        if key in {"reports", "analyses", "evidence", "errors"}
    }


def _run_read(run: AgentRun, requester_id: UUID) -> AgentRunRead:
    return AgentRunRead(
        id=run.id,
        agent_code=run.agent_code,
        trigger_code=run.trigger_code,
        status_code=run.status_code,
        llm_model_name=run.llm_model_name,
        prompt_version=run.prompt_version,
        requested_by_member_id=run.requested_by_member_id,
        report_id=run.report_id,
        source_refs=run.source_refs,
        generation_input=_generation_input_read(run, requester_id),
        output_snapshot=_output_read(run, requester_id),
        evidence=run.evidence if generation_payload_visible(run, requester_id) else None,
        error_message=run.error_message,
        error_code=run.error_code,
        current_stage_code=run.current_stage_code,
        attempt_count=run.attempt_count or 0,
        payload_expires_at=_seoul(run.payload_expires_at),
        payload_redacted_at=_seoul(run.payload_redacted_at),
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        total_tokens=run.total_tokens,
        created_at=_seoul(run.created_at),
        heartbeat_at=_seoul(run.heartbeat_at),
        started_at=_seoul(run.started_at),
        finished_at=_seoul(run.finished_at),
    )


def _prompt_version(agent_code: str) -> str:
    return {
        "report_writing": report_writing.PROMPT_VERSION,
        "meeting_processing": meeting_processing.PROMPT_VERSION,
        "contract_management_select_candidates": (
            contract_management.SELECT_CANDIDATES_PROMPT_VERSION
        ),
        "contract_management_next_meeting": (
            contract_management.PROPOSE_NEXT_MEETING_PROMPT_VERSION
        ),
        "contract_management_briefing": contract_management.GENERATE_BRIEFING_PROMPT_VERSION,
        "schedule_management": schedule_management.PROMPT_VERSION,
    }[agent_code]


def _request_hash(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _integrity_constraint(error: IntegrityError) -> str | None:
    original = getattr(error, "orig", None)
    cause = getattr(original, "__cause__", None)
    return next(
        (
            name
            for candidate in (original, cause, getattr(original, "diag", None))
            if (name := getattr(candidate, "constraint_name", None)) is not None
        ),
        None,
    )


def _request_source_refs(payload: AgentRunCreate) -> dict[str, Any]:
    refs = {}
    for field in (
        "customer_company_id",
        "sales_deal_id",
        "activity_id",
        "parent_run_id",
    ):
        value = getattr(payload, field)
        if value is not None:
            refs[field] = str(value)
    return refs


def _scope(member: Member):
    """같은 팀에서 관리자는 전체를, 일반 구성원은 본인 실행만 본다."""
    conditions = [AgentRun.team_id == member.team_id]
    if member.role_code == "member":
        conditions.append(AgentRun.requested_by_member_id == member.id)
    return conditions


async def _parent_run_or_409(
    db: AsyncSession, member: Member, parent_run_id: UUID, *, expected_agent_code: str
) -> AgentRun:
    """다른 실행을 이어받을 때, 같은 팀의 완료된 실행인지 확인한다."""
    conditions = [AgentRun.id == parent_run_id, AgentRun.team_id == member.team_id]
    if member.role_code == "member":
        # 시스템이 팀에 만든 제안은 담당자가 이어 쓸 수 있지만 다른 팀원의 수동 실행은 못 쓴다.
        conditions.append(
            or_(
                AgentRun.requested_by_member_id == member.id,
                AgentRun.requested_by_member_id.is_(None),
            )
        )
    parent = (await db.execute(select(AgentRun).where(*conditions))).scalar_one_or_none()
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="parent_run_not_found",
        )
    if parent.agent_code != expected_agent_code or parent.status_code != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="parent_run_not_usable",
        )
    return parent


async def _build_run_input(
    payload: AgentRunCreate, member: Member, db: AsyncSession
) -> tuple[str, dict[str, Any], dict[str, Any], UUID | None]:
    """agent_code 별로 prompt_version, input_snapshot, source_refs, parent_run_id 를 만든다."""
    if payload.agent_code == "contract_management_select_candidates":
        input_snapshot = await contract_schedule_snapshots.build_candidate_selection_snapshot(
            db, member
        )
        return (
            contract_management.SELECT_CANDIDATES_PROMPT_VERSION,
            input_snapshot,
            {},
            None,
        )

    if payload.agent_code == "contract_management_next_meeting":
        input_snapshot = await contract_schedule_snapshots.build_next_meeting_snapshot(
            db, member, payload.customer_company_id
        )
        return (
            contract_management.PROPOSE_NEXT_MEETING_PROMPT_VERSION,
            input_snapshot,
            {"customer_company_id": str(payload.customer_company_id)},
            None,
        )

    if payload.agent_code == "contract_management_briefing":
        # AI 제안(일정관리 실행)을 승인해서 만든 일정만 parent_run_id가 있다. 캘린더 직접
        # 입력이나 팀장 대리 입력처럼 AI 제안을 거치지 않은 일정은 부모 없이 진행한다.
        parent_id: UUID | None = None
        source_refs = {"activity_id": str(payload.activity_id)}
        if payload.parent_run_id is not None:
            parent = await _parent_run_or_409(
                db, member, payload.parent_run_id, expected_agent_code="schedule_management"
            )
            parent_id = parent.id
            source_refs["parent_run_id"] = str(parent.id)
        input_snapshot = await contract_schedule_snapshots.build_briefing_snapshot(
            db, member, payload.activity_id
        )
        source_refs["customer_company_id"] = input_snapshot["customer_company"]["id"]
        return (
            contract_management.GENERATE_BRIEFING_PROMPT_VERSION,
            input_snapshot,
            source_refs,
            parent_id,
        )

    # schedule_management. 계약관리 제안이 없어도(parent_run_id 없이) 실행할 수 있다.
    parent = None
    if payload.parent_run_id is not None:
        parent = await _parent_run_or_409(
            db,
            member,
            payload.parent_run_id,
            expected_agent_code="contract_management_next_meeting",
        )
    input_snapshot = await contract_schedule_snapshots.build_schedule_snapshot(
        db,
        member,
        payload.sales_deal_id,
        parent,
        payload.preferred_starts_at,
        payload.preferred_ends_at,
        payload.duration_minutes,
    )
    source_refs: dict[str, Any] = {"sales_deal_id": str(payload.sales_deal_id)}
    if parent is not None:
        source_refs["parent_run_id"] = str(parent.id)
    return (
        schedule_management.PROMPT_VERSION,
        input_snapshot,
        source_refs,
        parent.id if parent is not None else None,
    )


def generation_scope_key(payload: ReportGenerationCreate | ReportGenerationScope) -> str:
    """사용자 입력 ID 대신 검증된 보고 범위로 재진입 키를 만든다."""
    if payload.report_kind == "meeting":
        return f"meeting:{payload.source_activity_id}"
    if payload.report_kind == "daily":
        return f"daily:{payload.report_date.isoformat()}"
    return (
        f"{payload.report_kind}:{payload.period_start.isoformat()}:{payload.period_end.isoformat()}"
    )


def _generation_source_refs(payload: ReportGenerationCreate) -> dict[str, Any]:
    refs: dict[str, Any] = {
        "report_kind": payload.report_kind,
        "report_date": payload.report_date.isoformat(),
    }
    if payload.report_kind == "meeting":
        refs["source_activity_id"] = str(payload.source_activity_id)
        refs["sales_deal_ids"] = [str(value) for value in payload.sales_deal_ids]
    else:
        refs["period_start"] = (
            payload.period_start.isoformat() if payload.period_start is not None else None
        )
        refs["period_end"] = (
            payload.period_end.isoformat() if payload.period_end is not None else None
        )
    return refs


async def _report_generation_input(
    payload: ReportGenerationCreate,
    member: Member,
    db: AsyncSession,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    refs = _generation_source_refs(payload)
    if payload.report_kind == "meeting":
        assert payload.source_activity_id is not None and payload.transcript is not None
        snapshot = await meeting_processing.input_snapshot(
            db,
            member,
            payload.source_activity_id,
            payload.sales_deal_ids,
            payload.transcript,
        )
        return "meeting_processing", snapshot, refs

    # 기존 source 권한·기간 검사를 재사용하되 이 객체는 세션에 추가하지 않는다.
    transient = Report(
        id=uuid4(),
        team_id=member.team_id,
        author_member_id=member.id,
        recipient_member_id=None,
        template_snapshot=payload.template_snapshot,
        source_activity_id=None,
        sales_deal_id=None,
        customer_company_id=None,
        report_kind=payload.report_kind,
        report_date=payload.report_date,
        period_start=payload.period_start,
        period_end=payload.period_end,
        status_code="draft",
        content=payload.content,
        title=None,
        body=None,
        common_body=None,
        unassigned_body=None,
        structured_values={},
        transcript=None,
        source_snapshot=None,
        ai_evidence=None,
        version=1,
        generation_input_version=1,
        current_submission_id=None,
        note=None,
        review_note=None,
        reviewed_by_member_id=None,
        reviewed_at=None,
    )
    snapshot = report_writing.input_snapshot(transient, payload.guidance)
    snapshot["report_sources"] = await report_sources.build_report_sources(db, member, transient)
    activities = payload.content.get("activities", [])
    calendar_ids: list[UUID] = []
    for item in activities if isinstance(activities, list) else []:
        if not isinstance(item, dict) or item.get("included") is not True:
            continue
        if item.get("source") != "캘린더":
            continue
        try:
            calendar_ids.append(UUID(str(item["refId"])))
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(422, "report_source_id_invalid") from error
    if len(set(calendar_ids)) != len(calendar_ids):
        raise HTTPException(422, "report_source_duplicate")
    if calendar_ids:
        snapshot["report_sources"]["activities"] = await report_sources._source_activities(
            db, member, transient, calendar_ids
        )
    return "report_writing", snapshot, refs


async def create_report_generation(
    payload: ReportGenerationCreate,
    member: Member,
    db: AsyncSession,
) -> tuple[AgentRunRead, UUID | None]:
    """검증·권한 확인을 마친 생성 입력을 바로 고정하고 큐에 등록한다."""
    if not settings.llm_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="llm_not_configured",
        )
    requester_id = member.id
    request_hash = _request_hash(payload.model_dump(mode="json"))
    existing = (
        await db.execute(
            select(AgentRun).where(
                AgentRun.requested_by_member_id == requester_id,
                AgentRun.idempotency_key == payload.idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.request_hash != request_hash:
            raise HTTPException(409, "idempotency_key_reused")
        return _run_read(existing, requester_id), None

    try:
        agent_code, input_snapshot, source_refs = await _report_generation_input(
            payload, member, db
        )
        now = datetime.now(UTC)
        generation_input = payload.model_dump(mode="json", exclude={"idempotency_key"})
        run = AgentRun(
            id=uuid4(),
            team_id=member.team_id,
            parent_run_id=None,
            requested_by_member_id=requester_id,
            agent_code=agent_code,
            trigger_code="user",
            idempotency_key=payload.idempotency_key,
            report_id=None,
            status_code="queued",
            llm_model_name=settings.llm_model,
            prompt_version=_prompt_version(agent_code),
            # 이 값만 요청자에게 돌려준다. CRM이 포함된 input_snapshot은 응답하지 않는다.
            request_snapshot=generation_input,
            request_hash=request_hash,
            scope_key=generation_scope_key(payload),
            source_refs=source_refs,
            input_snapshot=input_snapshot,
            output_snapshot=None,
            evidence=None,
            error_message=None,
            error_code=None,
            current_stage_code="queued",
            attempt_count=0,
            payload_expires_at=now + REPORT_GENERATION_RETENTION,
            payload_redacted_at=None,
            lease_owner=None,
            lease_expires_at=None,
            heartbeat_at=None,
            next_attempt_at=now,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            created_at=now,
            started_at=None,
            finished_at=None,
        )
        db.add(run)
        await db.flush()
        read = _run_read(run, requester_id)
        await db.commit()
        return read, run.id
    except IntegrityError as error:
        await db.rollback()
        existing = (
            await db.execute(
                select(AgentRun).where(
                    AgentRun.requested_by_member_id == requester_id,
                    AgentRun.idempotency_key == payload.idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.request_hash != request_hash:
                raise HTTPException(409, "idempotency_key_reused") from None
            return _run_read(existing, requester_id), None
        if _integrity_constraint(error) == "agent_run_active_generation_scope_key":
            raise HTTPException(409, "report_generation_in_progress") from error
        raise
    except Exception:
        await db.rollback()
        raise


async def create(
    payload: AgentRunCreate,
    member: Member,
    db: AsyncSession,
) -> tuple[AgentRunRead, UUID | None]:
    """계약·일정 에이전트 요청을 영속 큐에 등록한다."""
    # LLM 설정이 없으면 큐에 쌓아둬도 반드시 실패한다. 만들기 전에 막는다.
    if not settings.llm_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="llm_not_configured",
        )

    requester_id = member.id
    request_snapshot = payload.model_dump(mode="json")
    request_hash = _request_hash(request_snapshot)
    # 같은 사용자가 동일 키로 재전송하면 새 실행 대신 기존 실행을 돌려준다.
    existing = (
        await db.execute(
            select(AgentRun).where(
                AgentRun.requested_by_member_id == requester_id,
                AgentRun.idempotency_key == payload.idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.request_hash is not None and existing.request_hash != request_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="idempotency_key_reused",
            )
        return _run_read(existing, requester_id), None

    parent_run_id = None
    try:
        if payload.parent_run_id is not None:
            expected_parent = {
                "contract_management_briefing": "schedule_management",
                "schedule_management": "contract_management_next_meeting",
            }[payload.agent_code]
            parent = await _parent_run_or_409(
                db, member, payload.parent_run_id, expected_agent_code=expected_parent
            )
            parent_run_id = parent.id
    except Exception:
        await db.rollback()
        raise

    now = datetime.now(UTC)
    try:
        run = AgentRun(
            id=uuid4(),
            team_id=member.team_id,
            parent_run_id=parent_run_id,
            requested_by_member_id=requester_id,
            agent_code=payload.agent_code,
            trigger_code="user",
            idempotency_key=payload.idempotency_key,
            report_id=None,
            status_code="queued",
            llm_model_name=settings.llm_model,
            prompt_version=_prompt_version(payload.agent_code),
            request_snapshot=request_snapshot,
            request_hash=request_hash,
            scope_key=None,
            source_refs=_request_source_refs(payload),
            # NOT NULL인 구 계약을 유지한다. worker가 만든 실제 입력으로 교체된다.
            input_snapshot={},
            output_snapshot=None,
            evidence=None,
            error_message=None,
            error_code=None,
            current_stage_code="queued",
            attempt_count=0,
            payload_expires_at=None,
            payload_redacted_at=None,
            lease_owner=None,
            lease_expires_at=None,
            heartbeat_at=None,
            next_attempt_at=now,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            created_at=now,
            started_at=None,
            finished_at=None,
        )
        db.add(run)
        await db.flush()
        read = _run_read(run, requester_id)
        await db.commit()
    except IntegrityError:
        # 동시에 들어온 같은 멱등키는 UNIQUE가 결정한다. 승자 실행을 그대로 반환한다.
        await db.rollback()
        existing = (
            await db.execute(
                select(AgentRun).where(
                    AgentRun.requested_by_member_id == requester_id,
                    AgentRun.idempotency_key == payload.idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        if existing.request_hash is not None and existing.request_hash != request_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="idempotency_key_reused",
            ) from None
        return _run_read(existing, requester_id), None
    except Exception:
        # 실행 이력이 일부만 저장되지 않도록 트랜잭션 전체를 되돌린다.
        await db.rollback()
        raise

    return read, run.id


async def execute(run_id: UUID) -> None:
    """기존 내부 호출용 진입점. 선점은 DB lease를 사용하므로 worker와 중복 실행되지 않는다."""
    from app.services.agent_worker import execute as execute_queued

    await execute_queued(run_id)


async def prepare_claimed(
    run: AgentRun, lease_owner: str
) -> tuple[str, dict[str, Any], UUID | None]:
    """신규 요청의 실제 입력을 만든다. 이미 만든 입력은 재시도에서도 그대로 재사용한다."""
    now = datetime.now(UTC)
    if run.agent_code in REPORT_GENERATION_CODES and (
        run.payload_redacted_at is not None
        or run.payload_expires_at is None
        or run.payload_expires_at <= now
    ):
        raise ValueError("agent_run_payload_expired")
    if run.request_hash is None:
        return run.agent_code, run.input_snapshot, run.requested_by_member_id
    if run.requested_by_member_id is None:
        raise ValueError("requester_required")

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        member = (
            await session.execute(
                select(Member).where(
                    Member.id == run.requested_by_member_id,
                    Member.team_id == run.team_id,
                    Member.active.is_(True),
                    Member.role_code.in_(("member", "manager")),
                )
            )
        ).scalar_one_or_none()
        if member is None:
            raise ValueError("requester_not_active")
        if run.input_snapshot:
            return run.agent_code, run.input_snapshot, run.requested_by_member_id
        request_snapshot = run.request_snapshot or {}
        if not request_snapshot or run.request_hash != _request_hash(request_snapshot):
            raise ValueError("request_hash_mismatch")
        payload = AgentRunCreate.model_validate(request_snapshot)
        prompt_version, input_snapshot, source_refs, parent_run_id = await _build_run_input(
            payload, member, session
        )
        values = {
            "prompt_version": prompt_version,
            "input_snapshot": input_snapshot,
            "source_refs": source_refs,
            "parent_run_id": parent_run_id,
            "current_stage_code": "running_agent",
        }
        result = await session.execute(
            update(AgentRun)
            .where(
                AgentRun.id == run.id,
                AgentRun.status_code == "running",
                AgentRun.lease_owner == lease_owner,
            )
            .values(**values)
        )
        if getattr(result, "rowcount", 1) == 0:
            raise RuntimeError("agent_run_lease_lost")
        await session.commit()
    return run.agent_code, input_snapshot, run.requested_by_member_id


async def dispatch(
    agent_code: str, input_snapshot: dict[str, Any], requested_by_member_id: UUID | None
) -> Any:
    """DB 연결을 쥐지 않고 에이전트 하나를 실행한다."""
    if agent_code == "report_writing":
        return await report_writing.run(input_snapshot)
    if agent_code == "meeting_processing":
        return await meeting_processing.run(input_snapshot)
    if agent_code == "contract_management_select_candidates":
        return await contract_management.select_next_meeting_candidates(input_snapshot)
    if agent_code == "contract_management_next_meeting":
        return await contract_management.propose_next_meeting(input_snapshot)
    if agent_code == "contract_management_briefing":
        return await contract_management.generate_briefing(input_snapshot)
    if agent_code == "schedule_management":
        return await schedule_management.run(input_snapshot)
    raise ValueError("unsupported_agent")


def evidence(agent_code: str, output: Any) -> dict[str, Any]:
    if agent_code == "report_writing":
        return {"prompt_version": report_writing.PROMPT_VERSION}
    if agent_code == "meeting_processing":
        return {
            "prompt_version": meeting_processing.PROMPT_VERSION,
            "deal_count": len(output.analyses),
            "unresolved_count": sum(
                item.applicability.scope in {"unresolved", "out_of_scope"}
                for item in output.evidence.items
            ),
            "errors": output.errors,
        }
    if agent_code == "contract_management_select_candidates":
        return {
            "prompt_version": contract_management.SELECT_CANDIDATES_PROMPT_VERSION,
            "candidate_count": len(output.candidates),
        }
    if agent_code == "contract_management_next_meeting":
        return {
            "prompt_version": contract_management.PROPOSE_NEXT_MEETING_PROMPT_VERSION,
            "risk_count": len(output.risks),
        }
    if agent_code == "contract_management_briefing":
        return {
            "prompt_version": contract_management.GENERATE_BRIEFING_PROMPT_VERSION,
            "risk_count": len(output.risks),
        }
    return {
        "prompt_version": schedule_management.PROMPT_VERSION,
        "candidate_count": len(output.schedule_candidates),
    }


def meeting_deal_evidence(
    run: AgentRun,
    sales_deal_ids: list[UUID],
) -> dict[UUID, dict[str, Any] | None]:
    """Extract only per-deal ML results/errors from a validated meeting run output."""
    try:
        output = meeting_processing.MeetingProcessingOutput.model_validate(run.output_snapshot)
    except (TypeError, ValueError):
        raise HTTPException(409, "report_generation_not_usable") from None
    expected = set(sales_deal_ids)
    actual = [item.sales_deal_id for item in output.analyses]
    if len(actual) != len(expected) or set(actual) != expected:
        raise HTTPException(409, "report_generation_not_usable")
    report_error = output.errors.get("report_writing")
    extracted: dict[UUID, dict[str, Any] | None] = {}
    for item in output.analyses:
        extracted[item.sales_deal_id] = {
            "meeting_run_id": str(run.id),
            "deal_assessment": (
                item.assessment.model_dump(mode="json") if item.assessment is not None else None
            ),
            # Feature extraction can succeed even when the downstream ML model fails.
            "features": (
                item.features.model_dump(mode="json") if item.features is not None else None
            ),
            "analysis_error": item.error,
            "report_error": report_error,
        }
    return extracted


def safe_error_code(error: BaseException) -> str:
    if isinstance(error, HTTPException) and isinstance(error.detail, str):
        candidate = error.detail
    elif isinstance(error, TimeoutError):
        return "agent_run_timeout"
    elif isinstance(error, DealModelError):
        candidate = str(error)
    elif isinstance(error, LLMError):
        candidate = str(error)
    elif isinstance(error, ValueError):
        candidate = str(error)
    else:
        return "agent_run_unexpected_error"
    return candidate if re.fullmatch(r"[A-Za-z0-9_:-]{1,120}", candidate) else "agent_run_failed"


def is_transient_error(error_code: str) -> bool:
    return is_transient_llm_error(error_code)


async def get(agent_run_id: UUID, member: Member, db: AsyncSession) -> AgentRunRead:
    """권한 밖의 실행은 존재 여부도 알리지 않고 404 로 답한다."""
    run = (
        await db.execute(select(AgentRun).where(AgentRun.id == agent_run_id, *_scope(member)))
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="agent_run_not_found",
        )
    return _run_read(run, member.id)


async def latest_generation(
    scope: ReportGenerationScope, member: Member, db: AsyncSession
) -> AgentRunRead:
    """현재 사용자의 아직 확정되지 않은 최신 생성 작업을 돌려준다."""
    run = (
        await db.execute(
            select(AgentRun)
            .where(
                AgentRun.team_id == member.team_id,
                AgentRun.requested_by_member_id == member.id,
                AgentRun.scope_key == generation_scope_key(scope),
                AgentRun.report_id.is_(None),
                AgentRun.payload_redacted_at.is_(None),
                AgentRun.payload_expires_at > datetime.now(UTC),
            )
            .order_by(AgentRun.created_at.desc().nullslast(), AgentRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="report_generation_not_found",
        )
    return _run_read(run, member.id)


def redact_payload(run: AgentRun, *, now: datetime | None = None) -> None:
    """확정된 보고서 생성 run에서 복구용 원문·CRM·AI 본문을 지운다."""
    if run.agent_code not in REPORT_GENERATION_CODES:
        return
    run.request_snapshot = {}
    run.input_snapshot = {}
    run.output_snapshot = None
    run.evidence = None
    run.payload_expires_at = None
    run.payload_redacted_at = now or datetime.now(UTC)


async def redact_expired_payloads(now: datetime | None = None) -> int:
    """복구 기한이 지난 생성은 원자적으로 중단하고 payload를 제거한다."""
    current = now or datetime.now(UTC)
    active = AgentRun.status_code.in_(("queued", "running"))
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        result = await session.execute(
            update(AgentRun)
            .where(
                AgentRun.agent_code.in_(REPORT_GENERATION_CODES),
                AgentRun.payload_redacted_at.is_(None),
                AgentRun.payload_expires_at.is_not(None),
                AgentRun.payload_expires_at <= current,
            )
            .values(
                status_code=case((active, "cancelled"), else_=AgentRun.status_code),
                current_stage_code=case((active, "cancelled"), else_=AgentRun.current_stage_code),
                error_code=case((active, "agent_run_payload_expired"), else_=AgentRun.error_code),
                error_message=case(
                    (active, "agent_run_payload_expired"), else_=AgentRun.error_message
                ),
                request_snapshot={},
                input_snapshot={},
                output_snapshot=None,
                evidence=None,
                payload_expires_at=None,
                payload_redacted_at=current,
                lease_owner=None,
                lease_expires_at=None,
                finished_at=case((active, current), else_=AgentRun.finished_at),
            )
        )
        await session.commit()
        return int(getattr(result, "rowcount", 0) or 0)
