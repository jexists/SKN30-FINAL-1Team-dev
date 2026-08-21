from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Response, status

from app.api.deps import CurrentMember, DbSession
from app.schemas.agent_runs import AgentRunCreate, AgentRunRead
from app.services import agent_runs as agent_run_service

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
    background: BackgroundTasks,
    member: CurrentMember,
    db: DbSession,
) -> AgentRunRead:
    """새 요청은 queued 로 등록하고 202 로 응답한다. 결과는 GET 으로 확인한다."""
    read, run_id = await agent_run_service.create(payload, member, db)
    # 멱등키로 재요청이면 run_id 가 없다. 기존 이력만 돌려주고 다시 실행하지 않는다.
    if run_id is not None:
        # ponytail: 초기 뼈대는 프로세스 내부 작업이다. 재시작 복구가 필요하면 영속 큐로 바꾼다.
        background.add_task(agent_run_service.execute, run_id)
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
