from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.core.config import settings
from app.db.session import get_engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """종료할 때 풀에 남은 커넥션을 반납한다.

    session pooler 슬롯은 프로젝트 전체가 나눠 쓰기 때문에, --reload 나 배포로
    프로세스가 갈릴 때 옛 커넥션이 pooler 쪽에서 정리되기를 기다리면 그 사이
    새 프로세스가 EMAXCONNSESSION 을 만난다. 나가면서 직접 끊어 준다.

    엔진은 처음 쓸 때 만들어지므로, DB 를 한 번도 안 쓴 프로세스에서는
    get_engine() 이 DATABASE_URL 을 요구하며 실패할 수 있다. 종료 경로가
    그것 때문에 깨지면 안 되니 조용히 넘어간다.
    """
    try:
        yield
    finally:
        # 예외나 취소로 나갈 때도 반납한다. 안 그러면 죽는 프로세스가 슬롯을 쥔 채 남는다.
        try:
            engine = get_engine()
        except RuntimeError:
            engine = None
        if engine is not None:
            await engine.dispose()


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
