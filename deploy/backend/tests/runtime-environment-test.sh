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

readonly VALID_ENVIRONMENT=$'APP_ENV=production\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\n'

valid_file="$(write_environment valid "${VALID_ENVIRONMENT}")"
valid_output="$(validate_runtime_environment "${valid_file}")" \
    || fail "valid production environment was rejected"
[[ -z "${valid_output}" ]] || fail "valid environment values were written to output"

assert_validation_fails \
    missing_app_env \
    'schema-required key is missing: APP_ENV' \
    '' \
    $'DEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\n'

assert_validation_fails \
    duplicate_app_env \
    'schema-required key is duplicated: APP_ENV' \
    '' \
    $'APP_ENV=production\nAPP_ENV=production\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\n'

assert_validation_fails \
    empty_app_env \
    'schema-required key is present but empty: APP_ENV' \
    '' \
    $'APP_ENV=\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\n'

assert_validation_fails \
    invalid_app_env_key \
    'Invalid runtime environment key syntax at line 1' \
    '' \
    $'APP_ENV =production\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\n'

readonly SECRET_MARKER='do-not-print-this-value'
assert_validation_fails \
    quoted_app_env \
    'APP_ENV must be the unquoted literal production; double-quoted form was provided' \
    "${SECRET_MARKER}" \
    $'APP_ENV="do-not-print-this-value"\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\n'

assert_validation_fails \
    whitespace_app_env \
    'APP_ENV must be the unquoted literal production; form with surrounding whitespace was provided' \
    '' \
    $'APP_ENV= production\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\n'

assert_validation_fails \
    commented_debug \
    'DEBUG must be the unquoted literal false; form with literal inline-comment text was provided' \
    '' \
    $'APP_ENV=production\nDEBUG=false # production\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\n'

assert_validation_fails \
    missing_cors \
    'production-security key is missing: CORS_ORIGINS' \
    '' \
    $'APP_ENV=production\nDEBUG=false\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\n'

assert_validation_fails \
    empty_database \
    'deployed-feature key is present but empty: DATABASE_URL' \
    '' \
    $'APP_ENV=production\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\n'

assert_validation_fails \
    bare_duplicate_app_env \
    'explicit KEY=value is required' \
    '' \
    $'APP_ENV=production\nAPP_ENV\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\n'

assert_validation_fails \
    malformed_unrelated_key \
    'Invalid runtime environment key syntax' \
    "${SECRET_MARKER}" \
    $'APP_ENV=production\nDEBUG=false\nCORS_ORIGINS=https://app.example.com\nDATABASE_URL=postgresql://example.invalid/app\nSUPABASE_PUBLISHABLE_KEY=synthetic-key\n=do-not-print-this-value\n'

raw_file="$(write_environment raw_value $'RAW_VALUE=  literal # text = preserved  \r\n')"
raw_value="$(dotenv_value "${raw_file}" RAW_VALUE)"
[[ "${raw_value}" == '  literal # text = preserved  ' ]] \
    || fail "dotenv_value changed the raw value"

upstream_file="$(write_environment upstream $'upstream salesluv_backend {\n    server 127.0.0.1:8000;\n}\n')"
[[ "$(read_backend_upstream_port "${upstream_file}")" == "8000" ]] \
    || fail "active Nginx upstream port was not parsed"
[[ "$(slot_container_for_port 8000)" == "${SLOT_8000_CONTAINER}" ]] \
    || fail "port 8000 did not map to its deployment slot"
[[ "$(other_backend_port 8000)" == "18000" ]] \
    || fail "inactive backend port was not selected"

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
