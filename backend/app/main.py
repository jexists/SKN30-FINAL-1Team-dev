from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.core.config import settings

app = FastAPI(
    title="SalesLuv API",
    description="고객·딜·일정·미팅 기록을 연결하는 다중 에이전트 기반 영업 업무 자동화 API",
    version="0.1.0",
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
