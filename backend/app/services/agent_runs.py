import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import contract_management, meeting_analysis, report_writing, schedule_management
from app.core.config import settings
from app.db.session import get_sessionmaker
from app.ml.deal_baseline import DealModelError
from app.models.agent import AgentRun
from app.models.content import Report
from app.models.workspace import Member
from app.schemas.agent_runs import AgentRunCreate, AgentRunRead
from app.services import contract_schedule_snapshots, meeting_processing
from app.services.llm import LLMError

_SEOUL = ZoneInfo("Asia/Seoul")


def _seoul(value: datetime | None) -> datetime | None:
    """DB 에는 UTC 로 두고 응답에서만 서울 시간으로 바꾼다."""
    return None if value is None else value.astimezone(_SEOUL)


def _run_read(run: AgentRun) -> AgentRunRead:
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
        output_snapshot=run.output_snapshot,
        evidence=run.evidence,
        error_message=run.error_message,
        error_code=run.error_code,
        apply_status=run.apply_status or "not_applicable",
        current_stage_code=run.current_stage_code,
        attempt_count=run.attempt_count or 0,
        base_report_version=run.base_report_version,
        base_generation_input_version=run.base_generation_input_version,
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
        "meeting_analysis": meeting_analysis.PROMPT_VERSION,
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
        "report_id",
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


async def _draft_source(db: AsyncSession, member: Member, report_id: UUID) -> Report:
    """초안 생성도 보고서 작성자만 시작한다."""
    conditions = [
        Report.id == report_id,
        Report.team_id == member.team_id,
    ]
    if member.role_code == "member":
        conditions.append(Report.author_member_id == member.id)
    report = (await db.execute(select(Report).where(*conditions))).scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="report_not_found",
        )
    if report.author_member_id != member.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="report_not_owned",
        )
    if report.status_code not in {"draft", "changes_requested"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="report_not_editable",
        )
    return report


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
    partial_applied = (
        expected_agent_code == "meeting_processing"
        and parent.status_code == "partial"
        and parent.apply_status == "applied"
    )
    if parent.agent_code != expected_agent_code or not (
        parent.status_code == "completed" or partial_applied
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="parent_run_not_usable",
        )
    return parent


async def _build_run_input(
    payload: AgentRunCreate, member: Member, db: AsyncSession
) -> tuple[str, dict[str, Any], dict[str, Any], UUID | None, int | None, int | None]:
    """agent_code 별로 prompt_version, input_snapshot, source_refs, parent_run_id 를 만든다."""
    if payload.agent_code == "meeting_processing":
        report = await _draft_source(db, member, payload.report_id)
        parent = None
        if payload.parent_run_id:
            parent = await _parent_run_or_409(
                db, member, payload.parent_run_id, expected_agent_code="meeting_processing"
            )
        snapshot = await meeting_processing.input_snapshot(
            db, member, report, parent, payload.assignment_overrides
        )
        return (
            meeting_processing.PROMPT_VERSION,
            snapshot,
            {
                "report_id": str(report.id),
                "activity_id": str(report.source_activity_id),
                "sales_deal_ids": list(snapshot["source"]["selected_deal_ids"]),
            },
            payload.parent_run_id,
            getattr(report, "version", None),
            getattr(report, "generation_input_version", None),
        )
    if payload.agent_code in ("report_writing", "meeting_analysis"):
        report = await _draft_source(db, member, payload.report_id)
        source_refs = {"report_id": str(report.id)}
        if report.sales_deal_id is not None:
            source_refs["sales_deal_id"] = str(report.sales_deal_id)
        if payload.agent_code == "report_writing":
            snapshot = report_writing.input_snapshot(report, payload.guidance)
            if report.report_kind != "meeting":
                from app.services.report_sources import build_report_sources

                snapshot["report_sources"] = await build_report_sources(db, member, report)
            return (
                report_writing.PROMPT_VERSION,
                snapshot,
                source_refs,
                None,
                getattr(report, "version", None),
                getattr(report, "generation_input_version", None),
            )
        try:
            input_snapshot = meeting_analysis.input_snapshot(report.transcript)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error
        return (
            meeting_analysis.PROMPT_VERSION,
            input_snapshot,
            source_refs,
            None,
            getattr(report, "version", None),
            getattr(report, "generation_input_version", None),
        )

    if payload.agent_code == "contract_management_select_candidates":
        input_snapshot = await contract_schedule_snapshots.build_candidate_selection_snapshot(
            db, member
        )
        return (
            contract_management.SELECT_CANDIDATES_PROMPT_VERSION,
            input_snapshot,
            {},
            None,
            None,
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
            None,
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
            None,
            None,
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
        None,
        None,
    )


async def create(
    payload: AgentRunCreate,
    member: Member,
    db: AsyncSession,
) -> tuple[AgentRunRead, UUID | None]:
    """원 요청만 먼저 영속화한다. CRM 조회와 프롬프트 입력 구성은 worker가 맡는다."""
    # LLM 설정이 없으면 큐에 쌓아둬도 반드시 실패한다. 만들기 전에 막는다.
    if not settings.llm_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="llm_not_configured",
        )

    request_snapshot = payload.model_dump(mode="json")
    request_hash = _request_hash(request_snapshot)
    # 같은 사용자가 동일 키로 재전송하면 새 실행 대신 기존 실행을 돌려준다.
    existing = (
        await db.execute(
            select(AgentRun).where(
                AgentRun.requested_by_member_id == member.id,
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
        return _run_read(existing), None

    # 권한 검증은 큐에 넣기 전에 끝낸다. CRM·과거 보고서 같은 비싼 스냅샷만 worker로 미룬다.
    parent_run_id = None
    base_report_version = None
    base_generation_input_version = None
    try:
        if payload.report_id is not None:
            report = await _draft_source(db, member, payload.report_id)
            base_report_version = getattr(report, "version", None)
            base_generation_input_version = getattr(report, "generation_input_version", None)
        if payload.parent_run_id is not None:
            expected_parent = {
                "meeting_processing": "meeting_processing",
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
            requested_by_member_id=member.id,
            agent_code=payload.agent_code,
            trigger_code="user",
            idempotency_key=payload.idempotency_key,
            report_id=payload.report_id,
            status_code="queued",
            llm_model_name=settings.llm_model,
            prompt_version=_prompt_version(payload.agent_code),
            request_snapshot=request_snapshot,
            request_hash=request_hash,
            source_refs=_request_source_refs(payload),
            # NOT NULL인 구 계약을 유지한다. worker가 만든 실제 입력으로 교체된다.
            input_snapshot={},
            output_snapshot=None,
            evidence=None,
            error_message=None,
            error_code=None,
            apply_status=(
                "pending" if payload.agent_code == "meeting_processing" else "not_applicable"
            ),
            current_stage_code="queued",
            attempt_count=0,
            base_report_version=base_report_version,
            base_generation_input_version=base_generation_input_version,
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
        read = _run_read(run)
        await db.commit()
    except IntegrityError as error:
        # 동시에 들어온 같은 멱등키는 UNIQUE가 결정한다. 승자 실행을 그대로 반환한다.
        await db.rollback()
        existing = (
            await db.execute(
                select(AgentRun).where(
                    AgentRun.requested_by_member_id == member.id,
                    AgentRun.idempotency_key == payload.idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            if _integrity_constraint(error) == "agent_run_meeting_active_report_key":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="meeting_generation_in_progress",
                ) from error
            raise
        if existing.request_hash is not None and existing.request_hash != request_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="idempotency_key_reused",
            ) from None
        return _run_read(existing), None
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
    if run.input_snapshot:
        return run.agent_code, run.input_snapshot, run.requested_by_member_id

    request_snapshot = run.request_snapshot or {}
    if not request_snapshot:
        # 전환 전에 만들어진 실행은 빈 입력도 유효할 수 있다.
        return run.agent_code, run.input_snapshot, run.requested_by_member_id
    if run.request_hash != _request_hash(request_snapshot):
        raise ValueError("request_hash_mismatch")
    payload = AgentRunCreate.model_validate(request_snapshot)
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
        (
            prompt_version,
            input_snapshot,
            source_refs,
            parent_run_id,
            report_version,
            generation_input_version,
        ) = await _build_run_input(payload, member, session)
        if (
            run.base_generation_input_version is not None
            and generation_input_version != run.base_generation_input_version
        ):
            raise ValueError("report_source_changed")
        if (
            run.base_generation_input_version is None
            and run.base_report_version is not None
            and report_version != run.base_report_version
        ):
            raise ValueError("report_source_changed")
        values = {
            "prompt_version": prompt_version,
            "input_snapshot": input_snapshot,
            "source_refs": source_refs,
            "parent_run_id": parent_run_id,
            "current_stage_code": "running_agent",
        }
        if run.base_report_version is None:
            values["base_report_version"] = report_version
        if run.base_generation_input_version is None:
            values["base_generation_input_version"] = generation_input_version
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
    if agent_code == "meeting_analysis":
        return await meeting_analysis.run(input_snapshot)
    if agent_code == "meeting_processing":
        return await meeting_processing.run(input_snapshot, requested_by_member_id)
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
        return {"prompt_version": report_writing.PROMPT_VERSION, "summary": output.summary}
    if agent_code == "meeting_analysis":
        return {
            "prompt_version": meeting_analysis.PROMPT_VERSION,
            "model_version": output.deal_assessment.model_version,
        }
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
    if error_code.endswith("_timeout"):
        return True
    if error_code.startswith("llm_request_failed:"):
        return error_code.rsplit(":", 1)[-1] in {
            "ConnectError",
            "ConnectTimeout",
            "PoolTimeout",
            "ReadError",
            "ReadTimeout",
            "RemoteProtocolError",
            "WriteError",
            "WriteTimeout",
        }
    if error_code.startswith("llm_provider_error:"):
        try:
            status_code = int(error_code.rsplit(":", 1)[-1])
        except ValueError:
            return False
        return status_code == 429 or status_code >= 500
    return False


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
    return _run_read(run)


async def latest_for_report(report_id: UUID, member: Member, db: AsyncSession) -> AgentRunRead:
    report_conditions = [Report.id == report_id, Report.team_id == member.team_id]
    if member.role_code == "member":
        report_conditions.append(Report.author_member_id == member.id)
    report_exists = (
        await db.execute(select(Report.id).where(*report_conditions))
    ).scalar_one_or_none()
    if report_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="report_not_found",
        )
    run = (
        await db.execute(
            select(AgentRun)
            .where(
                AgentRun.report_id == report_id,
                AgentRun.team_id == member.team_id,
                AgentRun.agent_code == "meeting_processing",
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
    return _run_read(run)
