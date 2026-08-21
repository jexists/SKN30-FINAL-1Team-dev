from datetime import UTC, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import report_writing
from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.agent import AgentRun
from app.models.content import Report
from app.models.workspace import Member
from app.schemas.agent_runs import AgentRunCreate, AgentRunRead
from app.services.llm import LLMError

_SEOUL = ZoneInfo("Asia/Seoul")


def _seoul(value: datetime | None) -> datetime | None:
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
    """실행 이력은 같은 팀 안에서 요청자 본인 것만 본다."""
    conditions = [AgentRun.team_id == member.team_id]
    if member.role_code == "member":
        conditions.append(AgentRun.requested_by_member_id == member.id)
    return conditions


async def _draft_source(db: AsyncSession, member: Member, report_id: UUID) -> Report:
    """초안을 붙일 보고서. 남의 보고서와 제출된 보고서는 대상이 아니다."""
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


async def create(
    payload: AgentRunCreate,
    member: Member,
    db: AsyncSession,
) -> tuple[AgentRunRead, UUID | None]:
    """실행 이력을 만들고 새 실행이면 백그라운드 작업용 id 도 돌려준다."""
    if not settings.llm_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="llm_not_configured",
        )

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
        report = await _draft_source(db, member, payload.report_id)
        run = AgentRun(
            id=uuid4(),
            team_id=member.team_id,
            parent_run_id=None,
            requested_by_member_id=member.id,
            agent_code=payload.agent_code,
            trigger_code="user",
            idempotency_key=payload.idempotency_key,
            status_code="queued",
            llm_model_name=settings.llm_model,
            prompt_version=report_writing.PROMPT_VERSION,
            source_refs={"report_id": str(report.id)},
            input_snapshot=report_writing.input_snapshot(report, payload.guidance),
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
        await db.rollback()
        raise

    return read, run.id


async def execute(run_id: UUID) -> None:
    """백그라운드 실행. 요청 세션이 닫힌 뒤라 자체 세션을 쓴다."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        run = (
            await session.execute(select(AgentRun).where(AgentRun.id == run_id))
        ).scalar_one_or_none()
        if run is None or run.status_code != "queued":
            return
        run.status_code = "running"
        run.started_at = datetime.now(UTC)
        await session.commit()

    output: report_writing.ReportDraftOutput | None = None
    error: str | None = None
    try:
        async with sessionmaker() as session:
            snapshot = (
                await session.execute(select(AgentRun.input_snapshot).where(AgentRun.id == run_id))
            ).scalar_one()
        output = await report_writing.run(snapshot)
    except LLMError as caught:
        error = str(caught)
    except Exception:
        # 공급자 예외 원문에 URL 이나 key 가 섞일 수 있어 코드만 남긴다.
        error = "llm_unexpected_error"

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
            # 제안일 뿐이다. 사람이 확인해 보고서에 반영하기 전에는 report 를 고치지 않는다.
            run.output_snapshot = output.model_dump()
            run.evidence = {
                "prompt_version": report_writing.PROMPT_VERSION,
                "summary": output.summary,
            }
        await session.commit()


async def get(agent_run_id: UUID, member: Member, db: AsyncSession) -> AgentRunRead:
    run = (
        await db.execute(select(AgentRun).where(AgentRun.id == agent_run_id, *_scope(member)))
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="agent_run_not_found",
        )
    return _run_read(run)
