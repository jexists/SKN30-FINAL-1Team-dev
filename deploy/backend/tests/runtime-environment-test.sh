#!/usr/bin/env bash

set -Eeuo pipefail

readonly TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${TEST_DIR}/../../.." && pwd)"

# shellcheck source=../deploy.sh
source "${PROJECT_ROOT}/deploy/backend/deploy.sh"

TEST_TMP_DIR="$(mktemp -d)"

cleanup_test_files() {
    rm -rf -- "${TEST_TMP_DIR}"
}

trap cleanup_test_files EXIT

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

write_environment() {
    local name="$1"
    local content="$2"
    local environment_file="${TEST_TMP_DIR}/${name}.env"

    printf '%s' "${content}" >"${environment_file}"
    printf '%s' "${environment_file}"
}

assert_validation_fails() {
    local name="$1"
    local expected_message="$2"
    local forbidden_text="$3"
    local content="$4"
    local environment_file
    local output

    environment_file="$(write_environment "${name}" "${content}")"
    if output="$(validate_runtime_environment "${environment_file}" 2>&1)"; then
        fail "${name} unexpectedly passed validation"
    fi
    [[ "${output}" == *"${expected_message}"* ]] \
        || fail "${name} did not report '${expected_message}': ${output}"
    if [[ -n "${forbidden_text}" && "${output}" == *"${forbidden_text}"* ]]; then
        fail "${name} exposed the rejected value"
    fi
}

readonly VALID_ENVIRONMENT=$'APP_ENV=production\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\nSUPABASE_SECRET_KEY=synthetic-secret\nADMIN_USER_IDS=aaaaaaaa-1111-4111-8111-111111111111\nFRONTEND_BASE_URL=https://app.example.com\n'

valid_file="$(write_environment valid "${VALID_ENVIRONMENT}")"
valid_output="$(validate_runtime_environment "${valid_file}")" \
    || fail "valid production environment was rejected"
[[ -z "${valid_output}" ]] || fail "valid environment values were written to output"

assert_validation_fails \
    missing_app_env \
    'schema-required key is missing: APP_ENV' \
    '' \
    $'DEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\nSUPABASE_SECRET_KEY=synthetic-secret\nADMIN_USER_IDS=aaaaaaaa-1111-4111-8111-111111111111\nFRONTEND_BASE_URL=https://app.example.com\n'

assert_validation_fails \
    duplicate_app_env \
    'schema-required key is duplicated: APP_ENV' \
    '' \
    $'APP_ENV=production\nAPP_ENV=production\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\nSUPABASE_SECRET_KEY=synthetic-secret\nADMIN_USER_IDS=aaaaaaaa-1111-4111-8111-111111111111\nFRONTEND_BASE_URL=https://app.example.com\n'

assert_validation_fails \
    empty_app_env \
    'schema-required key is present but empty: APP_ENV' \
    '' \
    $'APP_ENV=\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\nSUPABASE_SECRET_KEY=synthetic-secret\nADMIN_USER_IDS=aaaaaaaa-1111-4111-8111-111111111111\nFRONTEND_BASE_URL=https://app.example.com\n'

assert_validation_fails \
    invalid_app_env_key \
    'Invalid runtime environment key syntax at line 1' \
    '' \
    $'APP_ENV =production\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\nSUPABASE_SECRET_KEY=synthetic-secret\nADMIN_USER_IDS=aaaaaaaa-1111-4111-8111-111111111111\nFRONTEND_BASE_URL=https://app.example.com\n'

readonly SECRET_MARKER='do-not-print-this-value'
assert_validation_fails \
    quoted_app_env \
    'APP_ENV must be the unquoted literal production; double-quoted form was provided' \
    "${SECRET_MARKER}" \
    $'APP_ENV="do-not-print-this-value"\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\nSUPABASE_SECRET_KEY=synthetic-secret\nADMIN_USER_IDS=aaaaaaaa-1111-4111-8111-111111111111\nFRONTEND_BASE_URL=https://app.example.com\n'

assert_validation_fails \
    whitespace_app_env \
    'APP_ENV must be the unquoted literal production; form with surrounding whitespace was provided' \
    '' \
    $'APP_ENV= production\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\nSUPABASE_SECRET_KEY=synthetic-secret\nADMIN_USER_IDS=aaaaaaaa-1111-4111-8111-111111111111\nFRONTEND_BASE_URL=https://app.example.com\n'

assert_validation_fails \
    commented_debug \
    'DEBUG must be the unquoted literal false; form with literal inline-comment text was provided' \
    '' \
    $'APP_ENV=production\nDEBUG=false # production\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\nSUPABASE_SECRET_KEY=synthetic-secret\nADMIN_USER_IDS=aaaaaaaa-1111-4111-8111-111111111111\nFRONTEND_BASE_URL=https://app.example.com\n'

assert_validation_fails \
    missing_cors \
    'production-security key is missing: CORS_ORIGINS' \
    '' \
    $'APP_ENV=production\nDEBUG=false\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\nSUPABASE_SECRET_KEY=synthetic-secret\nADMIN_USER_IDS=aaaaaaaa-1111-4111-8111-111111111111\nFRONTEND_BASE_URL=https://app.example.com\n'

assert_validation_fails \
    empty_database \
    'deployed-feature key is present but empty: DATABASE_URL' \
    '' \
    $'APP_ENV=production\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\nSUPABASE_SECRET_KEY=synthetic-secret\nADMIN_USER_IDS=aaaaaaaa-1111-4111-8111-111111111111\nFRONTEND_BASE_URL=https://app.example.com\n'

# 계정 발급(/admin)이 의존하는 키다. 없으면 배포는 되고 발급만 503 으로 죽으므로
# 조용한 실패 대신 배포를 멈춘다.
assert_validation_fails \
    missing_supabase_secret \
    'deployed-feature key is missing: SUPABASE_SECRET_KEY' \
    '' \
    $'APP_ENV=production\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\nADMIN_USER_IDS=aaaaaaaa-1111-4111-8111-111111111111\nFRONTEND_BASE_URL=https://app.example.com\n'

assert_validation_fails \
    missing_admin_user_ids \
    'deployed-feature key is missing: ADMIN_USER_IDS' \
    '' \
    $'APP_ENV=production\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\nSUPABASE_SECRET_KEY=synthetic-secret\nFRONTEND_BASE_URL=https://app.example.com\n'

assert_validation_fails \
    bare_duplicate_app_env \
    'explicit KEY=value is required' \
    '' \
    $'APP_ENV=production\nAPP_ENV\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\nSUPABASE_SECRET_KEY=synthetic-secret\nADMIN_USER_IDS=aaaaaaaa-1111-4111-8111-111111111111\nFRONTEND_BASE_URL=https://app.example.com\n'

assert_validation_fails \
    malformed_unrelated_key \
    'Invalid runtime environment key syntax' \
    "${SECRET_MARKER}" \
    $'APP_ENV=production\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\nSUPABASE_SECRET_KEY=synthetic-secret\nADMIN_USER_IDS=aaaaaaaa-1111-4111-8111-111111111111\nFRONTEND_BASE_URL=https://app.example.com\n=do-not-print-this-value\n'

raw_file="$(write_environment raw_value $'RAW_VALUE=  literal # text = preserved  \r\n')"
raw_value="$(dotenv_value "${raw_file}" RAW_VALUE)"
[[ "${raw_value}" == '  literal # text = preserved  ' ]] \
    || fail "dotenv_value changed the raw value"

[[ "${DEAL_MODEL_VERSION}" == "deal-paper-rf-ensemble-v1" \
    && "${DEAL_MODEL_HOST_DIR}" == "/opt/salesluv-models/deal-paper-rf-ensemble-v1" \
    && "${#DEAL_MODEL_ARTIFACTS[@]}" == "1" \
    && "${DEAL_MODEL_ARTIFACTS[0]}" == "deal-paper-rf-ensemble-v1.joblib:609c5d63b201fcb125cca9cddc2fcbe229f76d3ebf0a1417466d027248b17681" ]] \
    || fail "deployment must use the verified single-file RF ensemble"

model_dir="${TEST_TMP_DIR}/model"
mkdir -p "${model_dir}"
printf 'model-bytes' >"${model_dir}/model.bin"
model_sha256="$(sha256sum "${model_dir}/model.bin")"
model_sha256="${model_sha256%%[[:space:]]*}"
validate_model_artifact "${model_dir}" model.bin "${model_sha256}" \
    || fail "valid model artifact was rejected"
if (validate_model_artifact "${model_dir}" model.bin wrong-sha) >/dev/null 2>&1; then
    fail "model artifact with the wrong hash was accepted"
fi

DOCKER_RUN_ARGS=()
docker() {
    DOCKER_RUN_ARGS=("$@")
    printf 'container-id\n'
}
start_production test-image test-container 18000
docker_run_args=" ${DOCKER_RUN_ARGS[*]} "
[[ "${docker_run_args}" == *" --env DEAL_MODEL_DIR=${DEAL_MODEL_CONTAINER_DIR} "* ]] \
    || fail "deal model container directory was not configured"
[[ "${docker_run_args}" == *" --mount type=bind,source=${DEAL_MODEL_HOST_DIR},target=${DEAL_MODEL_CONTAINER_DIR},readonly "* ]] \
    || fail "deal model directory was not mounted read-only"
start_agent_worker test-image test-worker
worker_run_args=" ${DOCKER_RUN_ARGS[*]} "
[[ "${worker_run_args}" == *" --name test-worker "* \
    && "${worker_run_args}" == *" /app/.venv/bin/python -m app.services.agent_worker "* \
    && "${worker_run_args}" != *" --publish "* ]] \
    || fail "agent worker was not started as a private process from the backend image"
unset -f docker

DOCKER_WORKER_STATE='true 0'
docker() {
    if [[ "$*" == *'.State.ExitCode'* ]]; then
        printf 'running=%s restarts=%s exit_code=1\n' \
            "${DOCKER_WORKER_STATE%% *}" "${DOCKER_WORKER_STATE##* }"
    else
        printf '%s\n' "${DOCKER_WORKER_STATE}"
    fi
}
sleep() { :; }
wait_for_agent_worker test-worker \
    || fail "stable agent worker was rejected"
DOCKER_WORKER_STATE='true 1'
if worker_failure="$(wait_for_agent_worker test-worker 2>&1)"; then
    fail "restarting agent worker was accepted"
fi
[[ "${worker_failure}" == *'restarts=1 exit_code=1'* ]] \
    || fail "unstable agent worker diagnostics omitted restart and exit state"
unset -f sleep
unset -f docker

TIMEOUT_ARGS=()
timeout() {
    TIMEOUT_ARGS=("$@")
    shift 4
    "$@"
}
DOCKER_EXEC_ARGS=()
DOCKER_EXEC_STATUS=0
docker() {
    DOCKER_EXEC_ARGS=("$@")
    return "${DOCKER_EXEC_STATUS}"
}
validate_deal_model_runtime test-container
[[ "${TIMEOUT_ARGS[0]}" == "--foreground" \
    && "${TIMEOUT_ARGS[1]}" == "--signal=TERM" \
    && "${TIMEOUT_ARGS[2]}" == "--kill-after=10s" \
    && "${TIMEOUT_ARGS[3]}" == "${DEAL_MODEL_VALIDATION_TIMEOUT_SECONDS}s" \
    && "${TIMEOUT_ARGS[4]}" == "docker" \
    && "${DOCKER_EXEC_ARGS[0]}" == "exec" \
    && "${DOCKER_EXEC_ARGS[1]}" == "test-container" \
    && "${DOCKER_EXEC_ARGS[2]}" == "/app/.venv/bin/python" \
    && "${DOCKER_EXEC_ARGS[3]}" == "-c" \
    && "${DOCKER_EXEC_ARGS[4]}" == *"_load_models()"* ]] \
    || fail "candidate deal model validation command was not executed"
validate_agent_queue_schema_runtime test-container
[[ "${DOCKER_EXEC_ARGS[0]}" == "exec" \
    && "${DOCKER_EXEC_ARGS[1]}" == "test-container" \
    && "${DOCKER_EXEC_ARGS[2]}" == "/app/.venv/bin/python" \
    && "${DOCKER_EXEC_ARGS[3]}" == "-m" \
    && "${DOCKER_EXEC_ARGS[4]}" == "app.services.agent_worker" \
    && "${DOCKER_EXEC_ARGS[5]}" == "--check-schema" ]] \
    || fail "agent queue schema validation command was not executed"
DOCKER_EXEC_STATUS=1
if validate_deal_model_runtime test-container; then
    fail "candidate deal model validation failure was swallowed"
fi
if validate_agent_queue_schema_runtime test-container; then
    fail "agent queue schema validation failure was swallowed"
fi
unset -f timeout
unset -f docker

upstream_file="$(write_environment upstream $'upstream salesluv_backend {\n    server 127.0.0.1:8000;\n}\n')"
[[ "$(read_backend_upstream_port "${upstream_file}")" == "8000" ]] \
    || fail "active Nginx upstream port was not parsed"
[[ "$(slot_container_for_port 8000)" == "${SLOT_8000_CONTAINER}" ]] \
    || fail "port 8000 did not map to its deployment slot"
[[ "$(other_backend_port 8000)" == "18000" ]] \
    || fail "inactive backend port was not selected"

schema_check_line="$(awk '/Validating the AgentRun queue schema/ { print NR; exit }' \
    "${PROJECT_ROOT}/deploy/backend/deploy.sh")"
promotion_line="$(awk '/Switching Nginx upstream from port/ { print NR; exit }' \
    "${PROJECT_ROOT}/deploy/backend/deploy.sh")"
worker_start_line="$(awk '/Starting AgentRun worker .*after traffic promotion/ { print NR; exit }' \
    "${PROJECT_ROOT}/deploy/backend/deploy.sh")"
deployment_success_line="$(awk '/^DEPLOY_SUCCEEDED="true"$/ { print NR; exit }' \
    "${PROJECT_ROOT}/deploy/backend/deploy.sh")"
[[ "${schema_check_line}" =~ ^[0-9]+$ \
    && "${promotion_line}" =~ ^[0-9]+$ \
    && "${worker_start_line}" =~ ^[0-9]+$ \
    && "${deployment_success_line}" =~ ^[0-9]+$ \
    && schema_check_line -lt promotion_line \
    && promotion_line -lt worker_start_line \
    && worker_start_line -lt deployment_success_line ]] \
    || fail "candidate worker must start only after successful traffic promotion"

rewritten_upstream_file="${TEST_TMP_DIR}/rewritten-upstream.conf"
if ! rewrite_backend_upstream_port \
    "${upstream_file}" "${BACKEND_PORT_A}" "${BACKEND_PORT_B}" \
    >"${rewritten_upstream_file}"; then
    fail "Nginx upstream port rewrite failed"
fi
[[ "$(read_backend_upstream_port "${rewritten_upstream_file}")" == "18000" ]] \
    || fail "Nginx upstream port was not rewritten from 8000 to 18000"

docker() {
    if [[ "${DOCKER_TEST_STATE}" == "missing" ]]; then
        return 0
    fi
    return 1
}

DOCKER_TEST_STATE="missing"
if container_uses_backend_port "${SLOT_8000_CONTAINER}" "${BACKEND_PORT_A}"; then
    fail "a missing container was reported as active"
else
    container_status=$?
fi
[[ "${container_status}" == "1" ]] \
    || fail "a missing container did not return the normal inactive status"

DOCKER_TEST_STATE="daemon-error"
if container_uses_backend_port "${SLOT_8000_CONTAINER}" "${BACKEND_PORT_A}"; then
    fail "a Docker state error was reported as active"
else
    container_status=$?
fi
[[ "${container_status}" == "${CONTAINER_STATE_ERROR_STATUS}" ]] \
    || fail "a Docker state error was not distinguished from a missing container"
if find_active_container "${BACKEND_PORT_A}" >/dev/null; then
    fail "Docker state errors were ignored while finding the active container"
else
    container_status=$?
fi
[[ "${container_status}" == "${CONTAINER_STATE_ERROR_STATUS}" ]] \
    || fail "find_active_container did not propagate the Docker state error"
unset -f docker

printf 'runtime environment validation tests passed\n'
