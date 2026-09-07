import asyncio
import json
from time import monotonic
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentMember, DbSession, get_current_member
from app.db.session import get_sessionmaker
from app.schemas.agent_runs import (
    AgentRunCreate,
    AgentRunRead,
    ReportGenerationCreate,
    ReportGenerationScope,
)
from app.services import agent_runs as agent_run_service
from app.services.agent_logging import log_agent_error
from app.services.agent_stream import progress_snapshot

router = APIRouter(tags=["agent-runs"])

# LLM 호출은 길어서 요청 안에서 끝내지 않는다. 클라이언트가 다시 조회할 간격만 알려준다.
RETRY_AFTER_SECONDS = 2


@router.post(
    "/agent-runs",
    response_model=AgentRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_agent_run(
    payload: AgentRunCreate,
    response: Response,
    member: CurrentMember,
    db: DbSession,
) -> AgentRunRead:
    """요청을 DB 큐에 먼저 등록한다. 별도 worker가 입력 구성부터 실행까지 맡는다."""
    read, _ = await agent_run_service.create(payload, member, db)
    # 어디를 언제 다시 조회할지 응답 헤더로 알려준다.
    response.headers["Location"] = f"/api/agent-runs/{read.id}"
    response.headers["Retry-After"] = str(RETRY_AFTER_SECONDS)
    return read


@router.get("/agent-runs/{agent_run_id}", response_model=AgentRunRead)
async def get_agent_run(
    agent_run_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> AgentRunRead:
    """진행 상태와 완료된 초안을 확인하는 폴링 대상."""
    return await agent_run_service.get(agent_run_id, member, db)


@router.post(
    "/report-generations",
    response_model=AgentRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_report_generation(
    payload: ReportGenerationCreate,
    response: Response,
    member: CurrentMember,
    db: DbSession,
) -> AgentRunRead:
    """보고서를 저장하지 않고 검증된 생성 입력만 AgentRun에 고정한다."""
    read, _ = await agent_run_service.create_report_generation(payload, member, db)
    response.headers["Location"] = f"/api/agent-runs/{read.id}"
    response.headers["Retry-After"] = str(RETRY_AFTER_SECONDS)
    return read


@router.get("/report-generations/latest", response_model=AgentRunRead)
async def latest_report_generation(
    scope: Annotated[ReportGenerationScope, Query()],
    member: CurrentMember,
    db: DbSession,
) -> AgentRunRead:
    return await agent_run_service.latest_generation(scope, member, db)


@router.get("/agent-runs/{agent_run_id}/events")
async def stream_agent_run(
    agent_run_id: UUID, request: Request, member: CurrentMember, db: DbSession
):
    """새 실행 없이 최신 미리보기와 DB의 확정 완료 상태를 전송한다."""
    viewer_id = member.id
    initial = await agent_run_service.get(agent_run_id, member, db)
    if not agent_run_service.generation_payload_visible(initial, viewer_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent_run_not_found")
    # 인증/접근 검사 트랜잭션도 스트리밍 동안 DB 연결을 점유하지 않는다.
    await db.rollback()

    def event(name, payload):
        return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def events():
        run = initial
        requester_id = viewer_id
        last_sequence = None
        next_check = monotonic() + RETRY_AFTER_SECONDS
        deadline = monotonic() + 25 * 60
        while not await request.is_disconnected():
            current_time = monotonic()
            if current_time >= deadline:
                yield event("error", {"detail": "agent_stream_timeout"})
                return
            if current_time >= next_check:
                try:
                    # 새 preview나 완료 본문보다 현재 계정·팀 권한을 먼저 다시 확인한다.
                    async with get_sessionmaker()() as session:
                        current = await get_current_member(request, session)
                        requester_id = current.id
                        run = await agent_run_service.get(agent_run_id, current, session)
                except HTTPException as error:
                    yield event("error", {"detail": error.detail})
                    return
                except Exception as error:
                    log_agent_error(
                        error,
                        stage="agent_stream",
                        run_id=str(agent_run_id),
                        error_code="agent_stream_unavailable",
                    )
                    yield event("error", {"detail": "agent_stream_unavailable"})
                    return
                next_check = monotonic() + RETRY_AFTER_SECONDS
                yield ": keep-alive\n\n"
            if not agent_run_service.generation_payload_visible(run, requester_id):
                yield event("error", {"detail": "agent_run_not_found"})
                return
            if run.status_code not in {"queued", "running"}:
                yield event("done", run.model_dump(mode="json"))
                return
            snapshot = progress_snapshot(agent_run_id)
            sequence = (run.status_code, snapshot["sequence"] if snapshot else -1)
            if sequence != last_sequence and (snapshot is not None or last_sequence is None):
                progress = snapshot or {
                    "run_id": str(agent_run_id),
                    "stage": run.current_stage_code or "starting",
                    "previews": [],
                }
                yield event("progress", {**progress, "status_code": run.status_code})
                last_sequence = sequence
            await asyncio.sleep(0.25)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
