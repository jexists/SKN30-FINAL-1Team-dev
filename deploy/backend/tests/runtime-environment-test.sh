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

disk_log="${TEST_TMP_DIR}/build-disk.log"
printf 'write /var/lib/containerd/io.containerd.content.v1.content/ingest/x/data: no space left on device\n' \
    >"${disk_log}"
build_log_shows_disk_exhaustion "${disk_log}" \
    || fail "disk exhaustion was not detected in the build log"
other_log="${TEST_TMP_DIR}/build-other.log"
printf 'ERROR: process "/bin/sh -c uv sync" did not complete successfully: exit code: 1\n' \
    >"${other_log}"
if build_log_shows_disk_exhaustion "${other_log}"; then
    fail "an unrelated build failure was reported as disk exhaustion"
fi
if build_log_shows_disk_exhaustion "${TEST_TMP_DIR}/missing-build.log"; then
    fail "a missing build log was reported as disk exhaustion"
fi

DOCKER_PRUNE_CALLS=()
DOCKER_PRUNE_HELP=""
docker() {
    if [[ "$*" == "builder prune --help" ]]; then
        printf '%s\n' "${DOCKER_PRUNE_HELP}"
        return 0
    fi
    DOCKER_PRUNE_CALLS+=(" $* ")
    return 0
}

assert_reclaim_is_safe() {
    local stage="$1"
    local call

    for call in "${DOCKER_PRUNE_CALLS[@]}"; do
        [[ "${call}" != *" volume prune "* ]] \
            || fail "${stage} reclaim removed Docker volumes"
        [[ "${call}" != *" system prune "* ]] \
            || fail "${stage} reclaim used system prune"
        [[ "${call}" != *" rm -f "* ]] \
            || fail "${stage} reclaim removed containers"
    done
    [[ " ${DOCKER_PRUNE_CALLS[*]} " == *" image prune -f "* ]] \
        || fail "${stage} reclaim did not remove dangling image layers"
}

assert_soft_reclaim_uses() {
    local help_output="$1"
    local expected="$2"

    DOCKER_PRUNE_CALLS=()
    DOCKER_PRUNE_HELP="${help_output}"
    reclaim_build_disk_space soft
    [[ " ${DOCKER_PRUNE_CALLS[*]} " == *" ${expected} "* ]] \
        || fail "soft reclaim did not run '${expected}': ${DOCKER_PRUNE_CALLS[*]}"
    [[ " ${DOCKER_PRUNE_CALLS[*]} " != *" builder prune -af "* ]] \
        || fail "soft reclaim dropped the entire build cache"
    assert_reclaim_is_safe soft
}

# 신 버전은 --max-used-space, 구 버전은 --keep-storage, 둘 다 없으면 시간 창으로 폴백한다.
assert_soft_reclaim_uses \
    '      --max-used-space bytes   Maximum amount of disk space' \
    "builder prune -f --max-used-space ${BUILD_CACHE_KEEP_BYTES}"
assert_soft_reclaim_uses \
    '      --keep-storage bytes     Amount of disk space to keep' \
    "builder prune -f --keep-storage ${BUILD_CACHE_KEEP_BYTES}"
assert_soft_reclaim_uses \
    '      --filter filter          Provide filter values' \
    "builder prune -f --filter until=${BUILD_CACHE_KEEP_WINDOW}"

DOCKER_PRUNE_CALLS=()
reclaim_build_disk_space hard
[[ " ${DOCKER_PRUNE_CALLS[*]} " == *" builder prune -af "* ]] \
    || fail "hard reclaim did not drop the build cache"
assert_reclaim_is_safe hard

DOCKER_PRUNE_CALLS=()
if reclaim_build_disk_space bogus >/dev/null 2>&1; then
    fail "an unsupported reclaim stage was accepted"
fi
((${#DOCKER_PRUNE_CALLS[@]} == 0)) \
    || fail "an unsupported reclaim stage still called Docker"

release_root="${TEST_TMP_DIR}/releases"
mkdir -p \
    "${release_root}/backend.aaa" \
    "${release_root}/backend.bbb" \
    "${release_root}/unrelated"
RELEASE_DIR="${release_root}/backend.aaa"
prune_stale_release_dirs "${release_root}" \
    || fail "abandoned release directory cleanup failed"
[[ -d "${release_root}/backend.aaa" ]] \
    || fail "the current release directory was removed"
[[ ! -d "${release_root}/backend.bbb" ]] \
    || fail "the abandoned release directory was kept"
[[ -d "${release_root}/unrelated" ]] \
    || fail "a directory outside the release prefix was removed"
RELEASE_DIR=""

disk_available_kib "${TEST_TMP_DIR}" >/dev/null \
    || fail "an existing directory could not be measured"
[[ "$(disk_available_kib "${TEST_TMP_DIR}")" =~ ^[0-9]+$ ]] \
    || fail "an existing directory did not yield a numeric measurement"
if disk_available_kib "${TEST_TMP_DIR}/missing-mount" >/dev/null 2>&1; then
    fail "a missing path was reported as measurable"
fi

# 측정 실패는 '가득 참'이 아니라 '모름'이다. 실패한 경로를 0으로 세면 최솟값이 0이 되어
# 멀쩡한 디스크에서 전면 정리가 발동한다.
DISK_PATH_READINGS=""
disk_available_kib() {
    local entry

    for entry in ${DISK_PATH_READINGS}; do
        if [[ "${entry%%:*}" == "$1" ]]; then
            [[ "${entry#*:}" != "fail" ]] || return 1
            printf '%s' "${entry#*:}"
            return 0
        fi
    done
    return 1
}

DISK_PATH_READINGS="/var/lib/containerd:900 /var/lib/docker:700"
[[ "$(available_disk_kib)" == "700" ]] \
    || fail "the smallest measurement was not selected"
DISK_PATH_READINGS="/var/lib/containerd:500 /var/lib/docker:800"
[[ "$(available_disk_kib)" == "500" ]] \
    || fail "the smallest measurement was not selected when listed first"

DISK_PATH_READINGS="/var/lib/containerd:600 /var/lib/docker:fail"
[[ "$(available_disk_kib)" == "600" ]] \
    || fail "a permission-denied path collapsed the measurement"
DISK_PATH_READINGS="/var/lib/docker:600"
[[ "$(available_disk_kib)" == "600" ]] \
    || fail "a missing path collapsed the measurement"

DISK_PATH_READINGS="/:1234"
[[ "$(available_disk_kib)" == "1234" ]] \
    || fail "the root filesystem fallback was not used"
DISK_PATH_READINGS=""
if available_disk_kib >/dev/null 2>&1; then
    fail "an entirely unmeasurable disk was reported as measured"
fi

RECLAIM_STAGES=()
reclaim_build_disk_space() {
    RECLAIM_STAGES+=("$1")
}
prune_stale_release_dirs() {
    return 0
}
DISK_READINGS=()
# available_disk_kib 는 명령 치환으로 호출되어 서브셸에서 실행되므로 남은 측정값은
# 파일로 넘긴다.
readonly DISK_READING_CURSOR="${TEST_TMP_DIR}/disk-reading-cursor"
available_disk_kib() {
    local index=0

    if [[ -s "${DISK_READING_CURSOR}" ]]; then
        index="$(<"${DISK_READING_CURSOR}")"
    fi
    if ((index + 1 < ${#DISK_READINGS[@]})); then
        printf '%s' "$((index + 1))" >"${DISK_READING_CURSOR}"
    fi
    printf '%s' "${DISK_READINGS[index]}"
}

set_disk_readings() {
    DISK_READINGS=("$@")
    : >"${DISK_READING_CURSOR}"
}

set_disk_readings "$((BUILD_MIN_FREE_KIB + 1))"
ensure_build_disk_space 2>/dev/null
((${#RECLAIM_STAGES[@]} == 0)) \
    || fail "cleanup ran even though free disk space was sufficient"

# soft 임계치 아래지만 임계 수위 위면 캐시를 남긴다. 여기서 hard 로 넘어가면 사실상
# 매 배포마다 캐시를 버리는 것과 같아진다.
RECLAIM_STAGES=()
set_disk_readings "$((BUILD_MIN_FREE_KIB - 1))" "$((BUILD_CRITICAL_FREE_KIB + 1))"
ensure_build_disk_space 2>/dev/null
[[ "${RECLAIM_STAGES[*]}" == "soft" ]] \
    || fail "moderate disk pressure escalated to a full cache drop: ${RECLAIM_STAGES[*]}"

RECLAIM_STAGES=()
set_disk_readings "$((BUILD_MIN_FREE_KIB - 1))" "$((BUILD_CRITICAL_FREE_KIB - 1))"
ensure_build_disk_space 2>/dev/null
[[ "${RECLAIM_STAGES[*]}" == "soft hard" ]] \
    || fail "critical disk pressure did not escalate to a full cache drop: ${RECLAIM_STAGES[*]}"

RECLAIM_STAGES=()
set_disk_readings "$((BUILD_MIN_FREE_KIB - 1))" "$((BUILD_MIN_FREE_KIB))"
ensure_build_disk_space 2>/dev/null
[[ "${RECLAIM_STAGES[*]}" == "soft" ]] \
    || fail "recovered disk space still triggered a full cache drop: ${RECLAIM_STAGES[*]}"

RECLAIM_STAGES=()
available_disk_kib() {
    return 1
}
ensure_build_disk_space 2>/dev/null \
    || fail "an unmeasurable disk blocked the deployment"
((${#RECLAIM_STAGES[@]} == 0)) \
    || fail "cleanup ran even though free disk space was unknown"

unset -f docker
unset -f reclaim_build_disk_space
unset -f prune_stale_release_dirs
unset -f available_disk_kib

printf 'runtime environment validation tests passed\n'
