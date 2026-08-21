from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Response, status

from app.api.deps import CurrentMember, DbSession
from app.schemas.agent_runs import AgentRunCreate, AgentRunRead
from app.services import agent_runs as agent_run_service

router = APIRouter(tags=["agent-runs"])

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
    read, run_id = await agent_run_service.create(payload, member, db)
    if run_id is not None:
        background.add_task(agent_run_service.execute, run_id)
    response.headers["Location"] = f"/api/agent-runs/{read.id}"
    response.headers["Retry-After"] = str(RETRY_AFTER_SECONDS)
    return read


@router.get("/agent-runs/{agent_run_id}", response_model=AgentRunRead)
async def get_agent_run(
    agent_run_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> AgentRunRead:
    return await agent_run_service.get(agent_run_id, member, db)
