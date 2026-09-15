#!/usr/bin/env bash
# DB에 저장된 AI 작업을 처리하는 개발용 worker

set -euo pipefail

cd "$(dirname "$0")/../backend"
exec uv run python -m app.services.agent_worker --poll-seconds 1
