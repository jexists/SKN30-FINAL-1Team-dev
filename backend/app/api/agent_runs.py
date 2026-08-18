from datetime import UTC, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentMember, DbSession
from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.agent import AgentRun
from app.models.content import Report
from app.models.workspace import Member
from app.schemas.agent_runs import (
    AgentRunCreate,
    AgentRunRead,
    ReportDraftOutput,
)
from app.services.llm import LLMError, generate_structured

router = APIRouter(tags=["agent-runs"])

_SEOUL = ZoneInfo("Asia/Seoul")

# 프롬프트를 고치면 올린다. 실행 이력이 어떤 프롬프트로 나왔는지 되짚기 위해서다.
PROMPT_VERSION = "report_writing.v1"
RETRY_AFTER_SECONDS = 2

_INSTRUCTIONS = (
    "너는 한국어 영업 보고서 초안을 쓰는 도우미다. "
    "주어진 양식 항목과 근거 자료만 사용하고 없는 사실을 지어내지 마라. "
    "각 항목마다 field_id 와 value 를 채우고, 근거가 없으면 value 를 빈 문자열로 둬라. "
    "JSON 만 출력한다."
)


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


def _input_snapshot(report: Report, guidance: str | None) -> dict:
    """실행에 실제로 쓴 값만 남긴다. 원문 전체를 복제하지 않는다."""
    return {
        "report_kind": report.report_kind,
        "report_date": report.report_date.isoformat(),
        "template_snapshot": report.template_snapshot,
        "content": report.content,
        "transcript": report.transcript,
        "guidance": guidance,
    }


def _prompt_input(snapshot: dict) -> str:
    lines = [
        f"보고서 종류: {snapshot['report_kind']}",
        f"보고 일자: {snapshot['report_date']}",
        f"양식: {snapshot['template_snapshot']}",
        f"현재 작성값: {snapshot['content']}",
    ]
    if snapshot.get("transcript"):
        lines.append(f"미팅 기록: {snapshot['transcript']}")
    if snapshot.get("guidance"):
        lines.append(f"작성자 요청: {snapshot['guidance']}")
    return "\n".join(lines)


async def _execute(run_id: UUID) -> None:
    """백그라운드 실행. 요청 세션이 닫힌 뒤라 자체 세션을 쓴다.

    실패해도 업무 데이터는 건드리지 않고 실행 이력에만 남긴다.
    """
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

    output: ReportDraftOutput | None = None
    error: str | None = None
    try:
        async with sessionmaker() as session:
            snapshot = (
                await session.execute(select(AgentRun.input_snapshot).where(AgentRun.id == run_id))
            ).scalar_one()
        output = await generate_structured(
            instructions=_INSTRUCTIONS,
            input_text=_prompt_input(snapshot),
            schema=ReportDraftOutput,
            schema_name="report_draft",
        )
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
            run.evidence = {"prompt_version": PROMPT_VERSION, "summary": output.summary}
        await session.commit()


@router.post(
    "/agent-runs",
    response_model=AgentRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_agent_run(
    payload: AgentRunCreate,
    response: Response,
    background: BackgroundTasks,
    member: CurrentMember,
    db: DbSession,
) -> AgentRunRead:
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
        response.headers["Location"] = f"/api/agent-runs/{existing.id}"
        response.headers["Retry-After"] = str(RETRY_AFTER_SECONDS)
        return _run_read(existing)

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
            prompt_version=PROMPT_VERSION,
            source_refs={"report_id": str(report.id)},
            input_snapshot=_input_snapshot(report, payload.guidance),
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

    background.add_task(_execute, run.id)
    response.headers["Location"] = f"/api/agent-runs/{run.id}"
    response.headers["Retry-After"] = str(RETRY_AFTER_SECONDS)
    return read


@router.get("/agent-runs/{agent_run_id}", response_model=AgentRunRead)
async def get_agent_run(
    agent_run_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> AgentRunRead:
    run = (
        await db.execute(select(AgentRun).where(AgentRun.id == agent_run_id, *_scope(member)))
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="agent_run_not_found",
        )
    return _run_read(run)
