#!/usr/bin/env bash
# 백엔드 개발 서버만 실행
#   bash scripts/backend.sh

set -euo pipefail

cd "$(dirname "$0")/.."

BACKEND_PORT="${BACKEND_PORT:-8000}"

[ -f backend/pyproject.toml ] || { echo "✗ backend/pyproject.toml 이 없습니다."; exit 1; }

free_port() {
  local port=$1
  local pids=''

  if command -v taskkill >/dev/null 2>&1; then
    pids=$(netstat -ano 2>/dev/null | awk -v pat=":${port}\$" '$2 ~ pat && $4 == "LISTENING" {print $5}' | sort -u)
    for wp in $pids; do
      taskkill //PID "$wp" //T //F >/dev/null 2>&1 || true
    done
  else
    pids=$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)
    for up in $pids; do
      kill -9 "$up" 2>/dev/null || true
    done
  fi

  if [ -n "$pids" ]; then
    echo "  포트 $port 를 쓰던 이전 프로세스를 정리했습니다."
  fi
}

free_port "$BACKEND_PORT"

echo "▶ 백엔드  http://localhost:${BACKEND_PORT}  (API 문서: /docs)"
cd backend
exec uv run uvicorn app.main:app --reload --port "$BACKEND_PORT"
