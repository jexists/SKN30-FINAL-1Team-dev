from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import contract_management, meeting_analysis, report_writing, schedule_management
from app.core.config import settings
from app.db.session import get_sessionmaker
from app.ml.deal_baseline import DealModelError
from app.models.agent import AgentRun
from app.models.content import Report
from app.models.workspace import Member
from app.schemas.agent_runs import AgentRunCreate, AgentRunRead
from app.services import contract_schedule_snapshots
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
        source_refs=run.source_refs,
        output_snapshot=run.output_snapshot,
        evidence=run.evidence,
        error_message=run.error_message,
        started_at=_seoul(run.started_at),
        finished_at=_seoul(run.finished_at),
    )


def _scope(member: Member):
    """같은 팀에서 관리자는 전체를, 일반 구성원은 본인 실행만 본다."""
    conditions = [AgentRun.team_id == member.team_id]
    if member.role_code == "member":
        conditions.append(AgentRun.requested_by_member_id == member.id)
    return conditions


async def _draft_source(db: AsyncSession, member: Member, report_id: UUID) -> Report:
    """초안을 붙일 draft 보고서. 일반 구성원은 본인 것만, 관리자는 팀 전체를 다룬다."""
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
    if report.status_code != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="report_not_editable",
        )
    return report


async def _parent_run_or_409(
    db: AsyncSession, member: Member, parent_run_id: UUID, *, expected_agent_code: str
) -> AgentRun:
    """다른 실행을 이어받을 때, 같은 팀의 완료된 실행인지 확인한다."""
    parent = (
        await db.execute(
            select(AgentRun).where(
                AgentRun.id == parent_run_id,
                AgentRun.team_id == member.team_id,
            )
        )
    ).scalar_one_or_none()
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
    if payload.agent_code in ("report_writing", "meeting_analysis"):
        report = await _draft_source(db, member, payload.report_id)
        source_refs = {"report_id": str(report.id)}
        if report.sales_deal_id is not None:
            source_refs["sales_deal_id"] = str(report.sales_deal_id)
        if payload.agent_code == "report_writing":
            return (
                report_writing.PROMPT_VERSION,
                report_writing.input_snapshot(report, payload.guidance),
                source_refs,
                None,
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


async def create(
    payload: AgentRunCreate,
    member: Member,
    db: AsyncSession,
) -> tuple[AgentRunRead, UUID | None]:
    """실행 이력을 만들고 새 실행이면 백그라운드 작업용 id 도 돌려준다."""
    # LLM 설정이 없으면 큐에 쌓아둬도 반드시 실패한다. 만들기 전에 막는다.
    if not settings.llm_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="llm_not_configured",
        )

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
        return _run_read(existing), None

    try:
        prompt_version, input_snapshot, source_refs, parent_run_id = await _build_run_input(
            payload, member, db
        )

        run = AgentRun(
            id=uuid4(),
            team_id=member.team_id,
            parent_run_id=parent_run_id,
            requested_by_member_id=member.id,
            agent_code=payload.agent_code,
            trigger_code="user",
            idempotency_key=payload.idempotency_key,
            # 실제 호출은 백그라운드에서 한다. 여기서는 대기 상태로만 남긴다.
            status_code="queued",
            llm_model_name=settings.llm_model,
            prompt_version=prompt_version,
            source_refs=source_refs,
            # 실행 시점 입력을 저장한다. 원본 데이터가 바뀌어도 이 실행에 쓴 입력은 남는다.
            input_snapshot=input_snapshot,
            output_snapshot=None,
            evidence=None,
            error_message=None,
            started_at=None,
            finished_at=None,
        )
        db.add(run)
        await db.flush()
        read = _run_read(run)
        await db.commit()
    except Exception:
        # 실행 이력이 일부만 저장되지 않도록 트랜잭션 전체를 되돌린다.
        await db.rollback()
        raise

    return read, run.id


async def execute(run_id: UUID) -> None:
    """백그라운드 실행. 요청 세션이 닫힌 뒤라 자체 세션을 쓴다."""
    sessionmaker = get_sessionmaker()
    # 1) 아직 queued 인 실행만 running 으로 바꾼다. 이미 처리된 재호출은 건너뛴다.
    # ponytail: 초기 단일 프로세스 전제. 다중 worker 에서는 조건부 UPDATE 로 선점한다.
    async with sessionmaker() as session:
        run = (
            await session.execute(select(AgentRun).where(AgentRun.id == run_id))
        ).scalar_one_or_none()
        if run is None or run.status_code != "queued":
            return
        run.status_code = "running"
        run.started_at = datetime.now(UTC)
        await session.commit()

        agent_code = run.agent_code
        input_snapshot = run.input_snapshot

    output: (
        report_writing.ReportDraftOutput
        | meeting_analysis.MeetingAnalysisOutput
        | contract_management.SelectNextMeetingCandidatesOutput
        | contract_management.NextMeetingProposalOutput
        | contract_management.ContractBriefingOutput
        | schedule_management.ScheduleManagementOutput
        | None
    ) = None
    error: str | None = None
    # 2) LLM 호출. 느린 구간이라 DB 커넥션을 쥐지 않은 채로 돈다.
    try:
        if agent_code == "report_writing":
            output = await report_writing.run(input_snapshot)
        elif agent_code == "meeting_analysis":
            output = await meeting_analysis.run(input_snapshot)
        elif agent_code == "contract_management_select_candidates":
            output = await contract_management.select_next_meeting_candidates(input_snapshot)
        elif agent_code == "contract_management_next_meeting":
            output = await contract_management.propose_next_meeting(input_snapshot)
        elif agent_code == "contract_management_briefing":
            output = await contract_management.generate_briefing(input_snapshot)
        elif agent_code == "schedule_management":
            output = await schedule_management.run(input_snapshot)
        else:
            error = "unsupported_agent"
    except LLMError as caught:
        error = str(caught)
    except DealModelError as caught:
        error = str(caught)
    except Exception:
        # 공급자 예외 원문에 URL 이나 key 가 섞일 수 있어 코드만 남긴다.
        error = "llm_unexpected_error"

    # 3) 결과 기록.
    async with sessionmaker() as session:
        run = (
            await session.execute(select(AgentRun).where(AgentRun.id == run_id))
        ).scalar_one_or_none()
        if run is None:
            return
        run.finished_at = datetime.now(UTC)
        if output is None:
            run.status_code = "failed"
            run.error_message = error
        else:
            run.status_code = "completed"
            run.output_snapshot = output.model_dump()
            if run.agent_code == "report_writing":
                # 제안일 뿐이다. 사람이 확인해 보고서에 반영하기 전에는 report 를 고치지 않는다.
                run.evidence = {
                    "prompt_version": report_writing.PROMPT_VERSION,
                    "summary": output.summary,
                }
            elif run.agent_code == "meeting_analysis":
                run.evidence = {
                    "prompt_version": meeting_analysis.PROMPT_VERSION,
                    "model_version": output.deal_assessment.model_version,
                }
            elif run.agent_code == "contract_management_select_candidates":
                run.evidence = {
                    "prompt_version": contract_management.SELECT_CANDIDATES_PROMPT_VERSION,
                    "candidate_count": len(output.candidates),
                }
            elif run.agent_code == "contract_management_next_meeting":
                run.evidence = {
                    "prompt_version": contract_management.PROPOSE_NEXT_MEETING_PROMPT_VERSION,
                    "risk_count": len(output.risks),
                }
            elif run.agent_code == "contract_management_briefing":
                run.evidence = {
                    "prompt_version": contract_management.GENERATE_BRIEFING_PROMPT_VERSION,
                    "risk_count": len(output.risks),
                }
            else:  # schedule_management
                run.evidence = {
                    "prompt_version": schedule_management.PROMPT_VERSION,
                    "candidate_count": len(output.schedule_candidates),
                }
        await session.commit()


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
