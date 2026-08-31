import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.core.config import settings
from app.services import agent_runs as agent_run_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """이전 프로세스가 남긴 실행 이력을 정리한 뒤 요청을 받는다."""
    try:
        recovered = await agent_run_service.recover_interrupted_runs()
    except Exception:
        # 정리는 뒷정리일 뿐이라, 실패해도 서버 기동 자체를 막지 않는다.
        logger.exception("중단된 실행 이력 회수 실패")
    else:
        if recovered:
            logger.info("중단된 실행 이력 %d 건을 failed 로 회수했습니다.", recovered)
    yield


app = FastAPI(
    title="SalesLuv API",
    description="고객·딜·일정·미팅 기록을 연결하는 다중 에이전트 기반 영업 업무 자동화 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error_without_submitted_values(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = []
    for error in exc.errors():
        safe_error = error.copy()
        safe_error.pop("input", None)
        errors.append(safe_error)
    return JSONResponse(status_code=422, content=jsonable_encoder({"detail": errors}))


@app.middleware("http")
async def require_allowed_origin(request: Request, call_next):
    if (
        request.url.path.startswith("/api/")
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.headers.get("origin") not in settings.cors_origin_list
    ):
        return JSONResponse(status_code=403, content={"detail": "origin_not_allowed"})
    return await call_next(request)


app.include_router(api_router, prefix="/api")
