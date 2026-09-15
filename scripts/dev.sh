#!/usr/bin/env bash
# 프론트엔드와 백엔드 개발 서버를 함께 실행
#   bash scripts/dev.sh

set -euo pipefail

cd "$(dirname "$0")/.."

if [ "$#" -gt 0 ]; then
  echo "사용법: bash scripts/dev.sh"
  echo "개별 실행: bash scripts/frontend.sh 또는 bash scripts/backend.sh"
  exit 2
fi

PIDS=()

stop_tree() {
  local pid=$1
  [ -n "$pid" ] || return 0

  if command -v taskkill >/dev/null 2>&1; then
    local winpid
    winpid=$(cat "/proc/$pid/winpid" 2>/dev/null || echo "$pid")
    taskkill //PID "$winpid" //T //F >/dev/null 2>&1 || true
  else
    pkill -TERM -P "$pid" 2>/dev/null || true
    kill -TERM "$pid" 2>/dev/null || true
  fi
}

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    stop_tree "$pid"
  done
}

trap cleanup EXIT
trap 'exit 130' INT TERM

bash scripts/backend.sh &
PIDS+=("$!")

bash scripts/frontend.sh &
PIDS+=("$!")

bash scripts/agent-worker.sh &
PIDS+=("$!")

echo
echo "종료하려면 Ctrl+C"
echo

# macOS 기본 Bash 3.2와 Git Bash에서 모두 동작하도록 wait -n 대신 폴링한다.
while true; do
  for pid in "${PIDS[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "▶ 한쪽 서버가 종료되어 나머지도 정리합니다."
      exit 0
    fi
  done
  sleep 1
done
