# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.12.5-python3.13-trixie-slim

WORKDIR /app

ENV UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./

# Runpod/Azure 장애 시 서버 자체에서 OCR을 재시도할 수 있도록 플랫폼 공통
# local OCR 의존성도 함께 설치한다. 모델 파일은 앱 설정의 캐시 경로에 첫
# 실행 때 준비되며, 이후 요청에서는 재사용된다.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra local \
    uv sync --frozen --no-dev --extra local \
    && chmod -R a=rX /app/.venv

COPY app ./app

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --create-home --no-log-init \
        --shell /usr/sbin/nologin appuser \
    && chmod -R a=rX /app/app

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
