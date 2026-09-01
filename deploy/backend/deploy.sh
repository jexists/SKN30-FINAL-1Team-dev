#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

readonly REPO_DIR="/opt/salesluv"
readonly RELEASES_DIR="/opt/salesluv-releases"
readonly ENV_FILE="/opt/salesluv/runtime/backend.env"
readonly ENV_DIR="${ENV_FILE%/*}"
readonly SSM_PARAMETER="/salesluv/production/backend/env"
readonly AWS_REGION="ap-northeast-2"
readonly LOCK_FILE="/var/lock/salesluv-backend-deploy.lock"

readonly DEAL_MODEL_VERSION="deal-paper-rf-ensemble-v1"
# ponytail: 단일 EC2의 버전 고정 디렉터리다. 호스트가 여러 대가 되면 S3 동기화로 바꾼다.
readonly DEAL_MODEL_HOST_DIR="/opt/salesluv-models/${DEAL_MODEL_VERSION}"
readonly DEAL_MODEL_CONTAINER_DIR="/app/pipeline/artifacts"
readonly -a DEAL_MODEL_ARTIFACTS=(
    "deal-paper-rf-ensemble-v1.joblib:609c5d63b201fcb125cca9cddc2fcbe229f76d3ebf0a1417466d027248b17681"
)

readonly IMAGE_REPOSITORY="salesluv-backend"
readonly LEGACY_PRODUCTION_CONTAINER="salesluv-backend"
readonly LEGACY_CANDIDATE_CONTAINER="salesluv-backend-candidate"
readonly SLOT_8000_CONTAINER="salesluv-backend-8000"
readonly SLOT_18000_CONTAINER="salesluv-backend-18000"
readonly WORKER_8000_CONTAINER="salesluv-agent-worker-8000"
readonly WORKER_18000_CONTAINER="salesluv-agent-worker-18000"
readonly BACKEND_PORT_A="8000"
readonly BACKEND_PORT_B="18000"

# Host Nginx must proxy_pass to http://salesluv_backend. This dedicated fragment
# must contain exactly one loopback server on BACKEND_PORT_A or BACKEND_PORT_B.
readonly NGINX_UPSTREAM_NAME="salesluv_backend"
readonly NGINX_UPSTREAM_FILE="/etc/nginx/conf.d/salesluv-backend-upstream.conf"
readonly CONTAINER_DRAIN_SECONDS="10"
readonly CONTAINER_STOP_TIMEOUT_SECONDS="30"

# 29GB 루트 디스크에서 구 이미지 + 신 이미지 + 빌드 캐시가 동시에 존재하는 최고점을
# 넘기기 위한 최소 여유 공간이다. 퍼센트 기준은 이 규모에서 너무 늦게 발동한다.
# 정리 강도를 임계치별로 나눈다. 16GiB 하나만 두고 자동으로 강도를 올리면 soft 정리로는
# 16GiB에 도달하지 못해 매 배포마다 캐시를 전부 버리게 되고, 빌드 시간이 매번 길어진다.
readonly BUILD_MIN_FREE_KIB="16777216"
readonly BUILD_CRITICAL_FREE_KIB="8388608"
# 시간 창은 배포 주기에 종속된다. 짧으면 공백 기간에 뜨거운 캐시를 버리고, 길면 최근 캐시만
# 있는 상태에서 아무것도 회수하지 못한다. 총량을 묶고 최근 사용분부터 남기는 쪽이 맞다.
readonly BUILD_CACHE_KEEP_BYTES="5GB"
readonly BUILD_CACHE_KEEP_WINDOW="72h"
# 이미지 export는 containerd 저장 영역에서, 빌드 캐시는 Docker 저장 영역에서 자란다.
# 같은 파일시스템이면 같은 값이 나오고, 분리돼 있으면 실제 병목을 잡는다.
readonly -a BUILD_DISK_PATHS=("/var/lib/containerd" "/var/lib/docker")

readonly HEALTH_ATTEMPTS="30"
readonly HEALTH_DELAY_SECONDS="2"
readonly HEALTH_TIMEOUT_SECONDS="5"
readonly DEAL_MODEL_VALIDATION_TIMEOUT_SECONDS="300"

readonly DOTENV_KEY_MISSING_STATUS="10"
readonly DOTENV_KEY_DUPLICATE_STATUS="11"
readonly CONTAINER_STATE_ERROR_STATUS="2"

TEMP_ENV_FILE=""
OLD_ENV_FILE=""
TEMP_UPSTREAM_FILE=""
OLD_UPSTREAM_FILE=""
RELEASE_DIR=""
BACKEND_CONTEXT=""
OLD_IMAGE=""
NEW_IMAGE_ID=""
ACTIVE_CONTAINER=""
ACTIVE_PORT=""
NEW_CONTAINER=""
ACTIVE_WORKER=""
NEW_WORKER=""
NEW_PORT=""
ENV_REPLACED="false"
IMAGE_BUILT="false"
PROMOTION_STARTED="false"
ROLLBACK_ATTEMPTED="false"
UPSTREAM_CHANGE_PENDING="false"
UPSTREAM_SWITCHED="false"
DEPLOY_SUCCEEDED="false"

die() {
    printf 'Deployment failed: %s\n' "$*" >&2
    exit 1
}

require_command() {
    local command_name="$1"

    command -v "${command_name}" >/dev/null 2>&1 \
        || die "required command not found: ${command_name}"
}

remove_release_dir() {
    if [[ -z "${RELEASE_DIR}" ]]; then
        return 0
    fi

    if [[ "${RELEASE_DIR}" != "${RELEASES_DIR}/backend.${DEPLOY_SHA}."* ]]; then
        printf 'Refusing to remove unexpected release directory: %s\n' \
            "${RELEASE_DIR}" >&2
        return 1
    fi

    rm -rf -- "${RELEASE_DIR}"
    RELEASE_DIR=""
    BACKEND_CONTEXT=""
}

restore_previous_environment() {
    if [[ "${ENV_REPLACED}" != "true" ]]; then
        return 0
    fi

    if [[ -n "${OLD_ENV_FILE}" && -f "${OLD_ENV_FILE}" ]]; then
        if ! mv -f -- "${OLD_ENV_FILE}" "${ENV_FILE}"; then
            printf 'Unable to restore the previous backend environment file.\n' >&2
            return 1
        fi
        OLD_ENV_FILE=""
    elif ! rm -f -- "${ENV_FILE}"; then
        printf 'Unable to remove the newly created backend environment file.\n' >&2
        return 1
    fi

    ENV_REPLACED="false"
}

# Print the unmodified value only when the key is assigned exactly once.
# Distinct statuses separate a missing key from a duplicated one.
dotenv_value() {
    local dotenv_file="$1"
    local expected_key="$2"

    awk -v expected_key="${expected_key}" '
        /^[[:space:]]*(#|$)/ { next }
        {
            line = $0
            sub(/\r$/, "", line)
            separator = index(line, "=")
            if (separator == 0) {
                next
            }

            key = substr(line, 1, separator - 1)
            sub(/^[[:space:]]+/, "", key)
            if (key != expected_key) {
                next
            }

            value = substr(line, separator + 1)

            matches++
            matched_value = value
        }
        END {
            if (matches == 0) {
                exit 10
            }
            if (matches > 1) {
                exit 11
            }
            printf "%s", matched_value
        }
    ' "${dotenv_file}"
}

dotenv_value_form() {
    local value="$1"

    case "${value}" in
        \"*|*\") printf 'double-quoted form' ;;
        \'*|*\') printf 'single-quoted form' ;;
        \`*|*\`) printf 'backtick-quoted form' ;;
        [[:space:]]*|*[[:space:]]) printf 'form with surrounding whitespace' ;;
        *'#'*) printf 'form with literal inline-comment text' ;;
        *'${'*) printf 'interpolation-like literal form' ;;
        *) printf 'different unquoted literal form' ;;
    esac
}

deployment_prerequisite_value() {
    local dotenv_file="$1"
    local expected_key="$2"
    local prerequisite_group="$3"
    local status
    local value

    if value="$(dotenv_value "${dotenv_file}" "${expected_key}")"; then
        [[ -n "${value}" ]] \
            || die "${prerequisite_group} key is present but empty: ${expected_key}"
        printf '%s' "${value}"
        return 0
    else
        status=$?
    fi

    case "${status}" in
        "${DOTENV_KEY_MISSING_STATUS}")
            die "${prerequisite_group} key is missing: ${expected_key}"
            ;;
        "${DOTENV_KEY_DUPLICATE_STATUS}")
            die "${prerequisite_group} key is duplicated: ${expected_key}"
            ;;
        *)
            die "unable to read ${prerequisite_group} key: ${expected_key}"
            ;;
    esac
}

validate_dotenv_syntax() {
    local dotenv_file="$1"

    if ! awk '
        {
            line = $0
            sub(/\r$/, "", line)
            if (line ~ /^[[:space:]]*(#|$)/) {
                next
            }

            separator = index(line, "=")
            if (separator == 0) {
                printf "Invalid runtime environment entry at line %d: explicit KEY=value is required.\n", NR > "/dev/stderr"
                invalid = 1
                exit
            }

            key = substr(line, 1, separator - 1)
            sub(/^[[:space:]]+/, "", key)
            if (key !~ /^[A-Za-z_][A-Za-z0-9_]*$/) {
                printf "Invalid runtime environment key syntax at line %d.\n", NR > "/dev/stderr"
                invalid = 1
                exit
            }
        }
        END {
            if (invalid) {
                exit 1
            }
        }
    ' "${dotenv_file}"; then
        die "runtime environment file has invalid dotenv syntax"
    fi
}

# 배포 전제 조건은 Settings 필드를 그대로 복제하지 않고 의미로 나눈다.
# 새 기능을 배포 필수로 바꿀 때는 이 함수, backend/app/core/config.py,
# 배포 설계 문서, SSM 파라미터, 준비 상태 프로브를 함께 갱신한다.
validate_runtime_environment() {
    local dotenv_file="$1"
    local feature_key
    local value

    validate_dotenv_syntax "${dotenv_file}"

    # 스키마 필수: Settings에 기본값이 없어 부재 시 애플리케이션이 뜨지 않는다.
    value="$(deployment_prerequisite_value \
        "${dotenv_file}" APP_ENV "schema-required")" || return 1
    [[ "${value}" == "production" ]] \
        || die "APP_ENV must be the unquoted literal production; $(
            dotenv_value_form "${value}"
        ) was provided"

    # 프로덕션 보안 조건
    value="$(deployment_prerequisite_value \
        "${dotenv_file}" DEBUG "production-security")" || return 1
    [[ "${value}" == "false" ]] \
        || die "DEBUG must be the unquoted literal false; $(
            dotenv_value_form "${value}"
        ) was provided"
    deployment_prerequisite_value \
        "${dotenv_file}" CORS_ORIGINS "production-security" >/dev/null || return 1

    # 런타임 기능 조건: /api/health/db, Supabase 인증, 계정 발급(/admin)이 의존한다.
    # SUPABASE_SECRET_KEY 가 없으면 계정 발급이 조용히 503 으로 죽으므로 여기서 막는다.
    for feature_key in \
        DATABASE_URL \
        SUPABASE_PUBLISHABLE_KEY \
        SUPABASE_SECRET_KEY \
        ADMIN_USER_IDS \
        FRONTEND_BASE_URL; do
        deployment_prerequisite_value \
            "${dotenv_file}" "${feature_key}" "deployed-feature" >/dev/null \
            || return 1
    done
}

validate_model_artifact() {
    local artifact_dir="$1"
    local filename="$2"
    local expected_sha256="$3"
    local artifact_path="${artifact_dir}/${filename}"
    local actual_sha256

    [[ -f "${artifact_path}" ]] \
        || die "deal model artifact is missing: ${artifact_path}"
    actual_sha256="$(sha256sum "${artifact_path}")" \
        || die "unable to hash deal model artifact: ${artifact_path}"
    actual_sha256="${actual_sha256%%[[:space:]]*}"
    [[ "${actual_sha256}" == "${expected_sha256}" ]] \
        || die "deal model artifact hash mismatch: ${artifact_path}"
}

validate_deal_model_artifacts() {
    local artifact
    local filename
    local expected_sha256

    for artifact in "${DEAL_MODEL_ARTIFACTS[@]}"; do
        IFS=: read -r filename expected_sha256 <<<"${artifact}"
        validate_model_artifact \
            "${DEAL_MODEL_HOST_DIR}" "${filename}" "${expected_sha256}"
    done
}

read_backend_upstream_port() {
    local upstream_file="$1"

    awk \
        -v port_a="${BACKEND_PORT_A}" \
        -v port_b="${BACKEND_PORT_B}" '
        {
            line = $0
            sub(/\r$/, "", line)
            sub(/[[:space:]]*#.*/, "", line)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
            gsub(/[[:space:]]+/, " ", line)

            if (line !~ /^server /) {
                next
            }

            if (line == "server 127.0.0.1:" port_a ";") {
                matches++
                matched_port = port_a
            } else if (line == "server 127.0.0.1:" port_b ";") {
                matches++
                matched_port = port_b
            } else {
                invalid_server = 1
            }
        }
        END {
            if (invalid_server || matches != 1) {
                exit 1
            }
            print matched_port
        }
    ' "${upstream_file}"
}

rewrite_backend_upstream_port() {
    local upstream_file="$1"
    local expected_port="$2"
    local next_port="$3"

    sed -E \
        "s#^([[:space:]]*server[[:space:]]+127\\.0\\.0\\.1:)${expected_port}([[:space:]]*;.*)\$#\\1${next_port}\\2#" \
        "${upstream_file}"
}

validated_backend_upstream_port() {
    local nginx_configuration
    local upstream_port

    [[ -f "${NGINX_UPSTREAM_FILE}" && ! -L "${NGINX_UPSTREAM_FILE}" ]] \
        || die "Nginx upstream file is missing or is not a regular file: ${NGINX_UPSTREAM_FILE}"
    [[ "$(grep -Ec \
        "^[[:space:]]*upstream[[:space:]]+${NGINX_UPSTREAM_NAME}[[:space:]]*\\{" \
        "${NGINX_UPSTREAM_FILE}")" == "1" ]] \
        || die "Nginx upstream file must define ${NGINX_UPSTREAM_NAME} exactly once"

    upstream_port="$(read_backend_upstream_port "${NGINX_UPSTREAM_FILE}")" \
        || die "Nginx upstream must contain exactly one supported loopback backend server"

    nginx_configuration="$(nginx -T 2>&1)" \
        || die "Nginx configuration is invalid before deployment"
    grep -Eq \
        "^[[:space:]]*proxy_pass[[:space:]]+http://${NGINX_UPSTREAM_NAME}([/;]|[[:space:]])" \
        <<<"${nginx_configuration}" \
        || die "Nginx does not proxy requests through ${NGINX_UPSTREAM_NAME}"
    grep -Eq \
        "^[[:space:]]*server[[:space:]]+127\\.0\\.0\\.1:${upstream_port}[[:space:]]*;" \
        <<<"${nginx_configuration}" \
        || die "Nginx configuration dump does not contain backend port ${upstream_port}"

    printf '%s' "${upstream_port}"
}

slot_container_for_port() {
    case "$1" in
        "${BACKEND_PORT_A}") printf '%s' "${SLOT_8000_CONTAINER}" ;;
        "${BACKEND_PORT_B}") printf '%s' "${SLOT_18000_CONTAINER}" ;;
        *) return 1 ;;
    esac
}

other_backend_port() {
    case "$1" in
        "${BACKEND_PORT_A}") printf '%s' "${BACKEND_PORT_B}" ;;
        "${BACKEND_PORT_B}") printf '%s' "${BACKEND_PORT_A}" ;;
        *) return 1 ;;
    esac
}

container_uses_backend_port() {
    local container_name="$1"
    local expected_port="$2"
    local binding
    local container_names
    local running

    if ! container_names="$(
        docker container ls --all --format '{{.Names}}'
    )"; then
        return "${CONTAINER_STATE_ERROR_STATUS}"
    fi
    grep -Fxq "${container_name}" <<<"${container_names}" || return 1

    if ! running="$(docker container inspect \
        --format '{{.State.Running}}' "${container_name}")"; then
        return "${CONTAINER_STATE_ERROR_STATUS}"
    fi
    [[ "${running}" == "true" ]] || return 1

    if ! binding="$(docker container inspect \
        --format '{{with index .NetworkSettings.Ports "8000/tcp"}}{{range .}}{{.HostIp}}:{{.HostPort}}{{"\n"}}{{end}}{{end}}' \
        "${container_name}")"; then
        return "${CONTAINER_STATE_ERROR_STATUS}"
    fi
    [[ "${binding}" == "127.0.0.1:${expected_port}" ]]
}

find_active_container() {
    local active_port="$1"
    local candidate_name
    local candidate_status
    local matched_container=""
    local matches=0

    for candidate_name in \
        "${SLOT_8000_CONTAINER}" \
        "${SLOT_18000_CONTAINER}" \
        "${LEGACY_PRODUCTION_CONTAINER}" \
        "${LEGACY_CANDIDATE_CONTAINER}"; do
        if container_uses_backend_port "${candidate_name}" "${active_port}"; then
            matched_container="${candidate_name}"
            ((matches += 1))
        else
            candidate_status=$?
            if [[ "${candidate_status}" == "${CONTAINER_STATE_ERROR_STATUS}" ]]; then
                return "${CONTAINER_STATE_ERROR_STATUS}"
            fi
        fi
    done

    ((matches <= 1)) || return 1
    printf '%s' "${matched_container}"
}

restore_backend_upstream() {
    [[ -n "${OLD_UPSTREAM_FILE}" && -f "${OLD_UPSTREAM_FILE}" ]] || return 0

    if ! TEMP_UPSTREAM_FILE="$(
        mktemp "${NGINX_UPSTREAM_FILE}.restore.XXXXXX"
    )"; then
        return 1
    fi
    if ! install -m 0644 "${OLD_UPSTREAM_FILE}" "${TEMP_UPSTREAM_FILE}"; then
        printf 'Unable to stage the previous Nginx upstream file.\n' >&2
        return 1
    fi
    if ! mv -f -- "${TEMP_UPSTREAM_FILE}" "${NGINX_UPSTREAM_FILE}"; then
        printf 'Unable to restore the previous Nginx upstream file.\n' >&2
        return 1
    fi
    TEMP_UPSTREAM_FILE=""
    if ! nginx -t >/dev/null; then
        printf 'The restored Nginx configuration is invalid.\n' >&2
        return 1
    fi
    if ! nginx -s reload >/dev/null; then
        printf 'Unable to reload the restored Nginx upstream.\n' >&2
        return 1
    fi

    if ! rm -f -- "${OLD_UPSTREAM_FILE}"; then
        printf 'Unable to remove the previous Nginx upstream backup.\n' >&2
        return 1
    fi
    OLD_UPSTREAM_FILE=""
    UPSTREAM_CHANGE_PENDING="false"
    UPSTREAM_SWITCHED="false"
}

switch_backend_upstream() {
    local expected_port="$1"
    local next_port="$2"
    local current_port

    current_port="$(read_backend_upstream_port "${NGINX_UPSTREAM_FILE}")" \
        || return 1
    [[ "${current_port}" == "${expected_port}" ]] || return 1

    if ! OLD_UPSTREAM_FILE="$(
        mktemp "${NGINX_UPSTREAM_FILE}.previous.XXXXXX"
    )"; then
        return 1
    fi
    if ! install -m 0600 "${NGINX_UPSTREAM_FILE}" "${OLD_UPSTREAM_FILE}"; then
        return 1
    fi
    UPSTREAM_CHANGE_PENDING="true"

    if ! TEMP_UPSTREAM_FILE="$(
        mktemp "${NGINX_UPSTREAM_FILE}.new.XXXXXX"
    )"; then
        return 1
    fi
    if ! rewrite_backend_upstream_port \
        "${NGINX_UPSTREAM_FILE}" "${expected_port}" "${next_port}" \
        >"${TEMP_UPSTREAM_FILE}"; then
        return 1
    fi
    if [[ "$(read_backend_upstream_port "${TEMP_UPSTREAM_FILE}")" != "${next_port}" ]]; then
        return 1
    fi

    if ! chmod 0644 "${TEMP_UPSTREAM_FILE}"; then
        return 1
    fi
    if ! mv -f -- "${TEMP_UPSTREAM_FILE}" "${NGINX_UPSTREAM_FILE}"; then
        return 1
    fi
    UPSTREAM_SWITCHED="true"
    TEMP_UPSTREAM_FILE=""

    if ! nginx -t >/dev/null; then
        restore_backend_upstream >/dev/null || true
        return 1
    fi
    if ! nginx -s reload >/dev/null; then
        restore_backend_upstream >/dev/null || true
        return 1
    fi
    if ! current_port="$(validated_backend_upstream_port)" \
        || [[ "${current_port}" != "${next_port}" ]]; then
        restore_backend_upstream >/dev/null || true
        return 1
    fi
}

cleanup() {
    local exit_status="$1"

    trap - EXIT
    trap '' HUP INT TERM
    set +e

    if [[ "${DEPLOY_SUCCEEDED}" != "true" ]]; then
        if [[ "${PROMOTION_STARTED}" == "true" \
            && "${ROLLBACK_ATTEMPTED}" != "true" ]]; then
            if ! rollback_production; then
                printf 'Automatic rollback did not complete successfully.\n' >&2
            fi
        elif [[ "${ENV_REPLACED}" == "true" ]]; then
            if ! restore_previous_environment; then
                printf 'Previous environment backup retained at: %s\n' \
                    "${OLD_ENV_FILE:-not available}" >&2
            fi
        fi
    fi

    if [[ -n "${TEMP_ENV_FILE}" ]]; then
        rm -f -- "${TEMP_ENV_FILE}" >/dev/null 2>&1 || true
    fi
    if [[ -n "${TEMP_UPSTREAM_FILE}" ]]; then
        rm -f -- "${TEMP_UPSTREAM_FILE}" >/dev/null 2>&1 || true
    fi
    if [[ -n "${OLD_ENV_FILE}" && "${ENV_REPLACED}" != "true" ]]; then
        rm -f -- "${OLD_ENV_FILE}" >/dev/null 2>&1 || true
        OLD_ENV_FILE=""
    elif [[ -n "${OLD_ENV_FILE}" ]]; then
        printf 'Previous environment backup retained at: %s\n' \
            "${OLD_ENV_FILE}" >&2
    fi

    if [[ -n "${OLD_UPSTREAM_FILE}" \
        && "${UPSTREAM_CHANGE_PENDING}" != "true" ]]; then
        rm -f -- "${OLD_UPSTREAM_FILE}" >/dev/null 2>&1 || true
        OLD_UPSTREAM_FILE=""
    elif [[ -n "${OLD_UPSTREAM_FILE}" ]]; then
        printf 'Previous Nginx upstream backup retained at: %s\n' \
            "${OLD_UPSTREAM_FILE}" >&2
    fi

    if [[ -n "${NEW_CONTAINER}" \
        && "${DEPLOY_SUCCEEDED}" != "true" \
        && "${UPSTREAM_SWITCHED}" != "true" ]]; then
        docker rm -f "${NEW_CONTAINER}" >/dev/null 2>&1 || true
    elif [[ -n "${NEW_CONTAINER}" \
        && "${DEPLOY_SUCCEEDED}" != "true" ]]; then
        printf 'New backend container retained because upstream rollback failed: %s\n' \
            "${NEW_CONTAINER}" >&2
    fi
    if [[ -n "${NEW_WORKER}" \
        && "${DEPLOY_SUCCEEDED}" != "true" ]]; then
        docker rm -f "${NEW_WORKER}" >/dev/null 2>&1 || true
    fi
    if [[ "${IMAGE_BUILT}" == "true" \
        && "${DEPLOY_SUCCEEDED}" != "true" \
        && "${UPSTREAM_SWITCHED}" != "true" ]]; then
        docker image rm "${NEW_IMAGE}" >/dev/null 2>&1 || true
    fi
    remove_release_dir >/dev/null 2>&1 || true
    exit "${exit_status}"
}

wait_for_backend() {
    local port="$1"
    local attempt

    for ((attempt = 1; attempt <= HEALTH_ATTEMPTS; attempt++)); do
        if curl --fail --silent --show-error \
            --connect-timeout "${HEALTH_TIMEOUT_SECONDS}" \
            --max-time "${HEALTH_TIMEOUT_SECONDS}" \
            "http://127.0.0.1:${port}/api/health" >/dev/null 2>&1 \
            && curl --fail --silent --show-error \
                --connect-timeout "${HEALTH_TIMEOUT_SECONDS}" \
                --max-time "${HEALTH_TIMEOUT_SECONDS}" \
                "http://127.0.0.1:${port}/api/health/db" >/dev/null 2>&1; then
            return 0
        fi

        if ((attempt < HEALTH_ATTEMPTS)); then
            sleep "${HEALTH_DELAY_SECONDS}"
        fi
    done

    printf 'Health checks failed on port %s after %s attempts.\n' \
        "${port}" "${HEALTH_ATTEMPTS}" >&2
    return 1
}

start_production() {
    local image="$1"
    local container_name="$2"
    local host_port="$3"

    docker run --detach \
        --name "${container_name}" \
        --restart unless-stopped \
        --log-driver json-file \
        --log-opt max-size=10m \
        --log-opt max-file=3 \
        --env-file "${ENV_FILE}" \
        --env "DEAL_MODEL_DIR=${DEAL_MODEL_CONTAINER_DIR}" \
        --mount "type=bind,source=${DEAL_MODEL_HOST_DIR},target=${DEAL_MODEL_CONTAINER_DIR},readonly" \
        --publish "127.0.0.1:${host_port}:8000" \
        "${image}" >/dev/null
}

worker_container_for_port() {
    case "$1" in
        "${BACKEND_PORT_A}") printf '%s' "${WORKER_8000_CONTAINER}" ;;
        "${BACKEND_PORT_B}") printf '%s' "${WORKER_18000_CONTAINER}" ;;
        *) return 1 ;;
    esac
}

start_agent_worker() {
    local image="$1"
    local container_name="$2"

    docker run --detach \
        --name "${container_name}" \
        --restart unless-stopped \
        --log-driver json-file \
        --log-opt max-size=10m \
        --log-opt max-file=3 \
        --env-file "${ENV_FILE}" \
        --env "DEAL_MODEL_DIR=${DEAL_MODEL_CONTAINER_DIR}" \
        --mount "type=bind,source=${DEAL_MODEL_HOST_DIR},target=${DEAL_MODEL_CONTAINER_DIR},readonly" \
        "${image}" \
        /app/.venv/bin/python -m app.services.agent_worker >/dev/null
}

validate_agent_queue_schema_runtime() {
    local container_name="$1"

    docker exec "${container_name}" \
        /app/.venv/bin/python -m app.services.agent_worker --check-schema
}

wait_for_agent_worker() {
    local container_name="$1"
    local attempt

    for ((attempt = 1; attempt <= 10; attempt++)); do
        if [[ "$(docker container inspect --format '{{.State.Running}}' \
            "${container_name}" 2>/dev/null || true)" == "true" ]]; then
            return 0
        fi
        sleep 1
    done
    return 1
}

validate_deal_model_runtime() {
    local container_name="$1"

    timeout --foreground --signal=TERM --kill-after=10s \
        "${DEAL_MODEL_VALIDATION_TIMEOUT_SECONDS}s" \
        docker exec "${container_name}" \
        /app/.venv/bin/python -c \
        'from app.ml.deal_baseline import _load_models; _load_models()'
}

rollback_production() {
    ROLLBACK_ATTEMPTED="true"
    printf 'Production promotion was interrupted; starting rollback.\n' >&2

    if ! restore_previous_environment; then
        printf 'Rollback could not restore the previous environment file.\n' >&2
        if [[ -n "${OLD_ENV_FILE}" ]]; then
            printf 'Previous environment backup retained at: %s\n' \
                "${OLD_ENV_FILE}" >&2
        fi
        return 1
    fi

    if [[ "${UPSTREAM_CHANGE_PENDING}" == "true" ]]; then
        if ! restore_backend_upstream; then
            printf 'Rollback could not restore the previous Nginx upstream.\n' >&2
            return 1
        fi
    fi

    if [[ -n "${ACTIVE_CONTAINER}" ]] \
        && ! wait_for_backend "${ACTIVE_PORT}"; then
        printf 'Previous backend container remained running, but rollback health checks failed.\n' >&2
        return 1
    fi

    if [[ -n "${NEW_CONTAINER}" ]]; then
        docker rm -f "${NEW_CONTAINER}" >/dev/null 2>&1 || true
    fi
    PROMOTION_STARTED="false"
    printf 'Previous backend upstream and environment restored.\n' >&2
}

disk_available_kib() {
    local target="$1"
    local df_output

    [[ -d "${target}" ]] || return 1

    # set -o pipefail 덕분에 df 실패(권한 거부 등)가 파이프라인으로 전파된다.
    # awk 가 빈 문자열을 내보내는 경우까지 막으려고 형식 검사를 한 번 더 둔다.
    df_output="$(df -Pk "${target}" 2>/dev/null | awk 'NR == 2 { print $4 }')" \
        || return 1
    [[ "${df_output}" =~ ^[0-9]+$ ]] || return 1

    printf '%s' "${df_output}"
}

# 측정에 실패한 경로는 건너뛸 뿐 0으로 세지 않는다. 실패를 0으로 취급하면 최솟값이 0이 되어
# 멀쩡한 디스크에서 빌드 캐시를 전부 버리게 된다. 측정 실패는 '가득 참'이 아니라 '모름'이다.
available_disk_kib() {
    local target
    local reading
    local smallest=""

    for target in "${BUILD_DISK_PATHS[@]}"; do
        if ! reading="$(disk_available_kib "${target}")"; then
            continue
        fi
        if [[ -z "${smallest}" ]] || ((reading < smallest)); then
            smallest="${reading}"
        fi
    done

    if [[ -z "${smallest}" ]]; then
        smallest="$(disk_available_kib "/")" || return 1
    fi

    printf '%s' "${smallest}"
}

prune_stale_release_dirs() {
    local releases_root="${1:-${RELEASES_DIR}}"
    local stale_dir
    local prune_failed="false"

    for stale_dir in "${releases_root}"/backend.*; do
        [[ -d "${stale_dir}" ]] || continue
        [[ "${stale_dir}" == "${releases_root}/backend."* ]] || continue
        if [[ -n "${RELEASE_DIR}" && "${stale_dir}" == "${RELEASE_DIR}" ]]; then
            continue
        fi

        if ! rm -rf -- "${stale_dir}"; then
            printf 'Unable to remove the abandoned release directory: %s\n' \
                "${stale_dir}" >&2
            prune_failed="true"
        fi
    done

    [[ "${prune_failed}" != "true" ]]
}

# Docker 버전에 따라 캐시 크기 상한 플래그 이름이 다르고 아예 없을 수도 있다.
# 신 버전의 --max-used-space 를 먼저 보고, 없으면 구 버전의 --keep-storage 를 쓴다.
builder_cache_limit_flag() {
    local help_output

    help_output="$(docker builder prune --help 2>/dev/null)" || return 0

    if [[ "${help_output}" == *"--max-used-space"* ]]; then
        printf -- '--max-used-space'
    elif [[ "${help_output}" == *"--keep-storage"* ]]; then
        printf -- '--keep-storage'
    fi
}

# 실행 중인 컨테이너, 태그된 백엔드 이미지, Docker 볼륨은 건드리지 않는다.
# image prune은 dangling 레이어만 제거하므로 롤백 대상인 OLD_IMAGE 는 남는다.
reclaim_build_disk_space() {
    local stage="$1"
    local limit_flag

    case "${stage}" in
    soft)
        limit_flag="$(builder_cache_limit_flag)"
        if [[ -n "${limit_flag}" ]]; then
            if ! docker builder prune -f \
                "${limit_flag}" "${BUILD_CACHE_KEEP_BYTES}" >/dev/null; then
                printf 'Unable to cap the Docker build cache size.\n' >&2
            fi
        elif ! docker builder prune -f \
            --filter "until=${BUILD_CACHE_KEEP_WINDOW}" >/dev/null; then
            printf 'Unable to reclaim the aged Docker build cache.\n' >&2
        fi
        ;;
    hard)
        if ! docker builder prune -af >/dev/null; then
            printf 'Unable to reclaim the Docker build cache.\n' >&2
        fi
        ;;
    *)
        printf 'Unsupported build disk reclaim stage: %s\n' "${stage}" >&2
        return 1
        ;;
    esac

    if ! docker image prune -f >/dev/null; then
        printf 'Unable to reclaim dangling Docker image layers.\n' >&2
    fi
}

ensure_build_disk_space() {
    local free_kib

    if ! free_kib="$(available_disk_kib)"; then
        printf 'Unable to measure free disk space; continuing without cleanup.\n' >&2
        return 0
    fi
    ((free_kib < BUILD_MIN_FREE_KIB)) || return 0

    printf 'Free disk space is %s KiB, below the %s KiB build threshold; reclaiming space.\n' \
        "${free_kib}" "${BUILD_MIN_FREE_KIB}" >&2
    prune_stale_release_dirs || true
    reclaim_build_disk_space soft

    if ! free_kib="$(available_disk_kib)"; then
        printf 'Unable to re-measure free disk space after cleanup.\n' >&2
        return 0
    fi
    # 16GiB 에 못 미쳐도 임계 수위(8GiB) 위라면 캐시를 남긴 채 빌드로 넘어간다.
    # 여기서 전면 정리를 돌리면 사실상 매 배포마다 캐시를 버리는 것과 같아진다.
    if ((free_kib >= BUILD_CRITICAL_FREE_KIB)); then
        printf 'Free disk space is %s KiB after cleanup; keeping the remaining build cache.\n' \
            "${free_kib}" >&2
        return 0
    fi

    printf 'Free disk space is still %s KiB, below the %s KiB critical threshold; dropping the entire Docker build cache.\n' \
        "${free_kib}" "${BUILD_CRITICAL_FREE_KIB}" >&2
    reclaim_build_disk_space hard

    if free_kib="$(available_disk_kib)"; then
        printf 'Free disk space after full build cache removal: %s KiB.\n' \
            "${free_kib}" >&2
    fi

    # 임계치에 못 미쳐도 빌드는 시도한다. 실제로 공간이 부족하면 빌드 실패를 감지해
    # 한 번 더 정리하고 재시도한다.
    return 0
}

build_log_shows_disk_exhaustion() {
    local build_log="$1"

    [[ -f "${build_log}" ]] || return 1
    grep -qi 'no space left on device' "${build_log}"
}

build_backend_image() {
    DOCKER_BUILDKIT=1 docker build --progress=plain \
        --tag "${NEW_IMAGE}" "${BACKEND_CONTEXT}" >"${BUILD_LOG}" 2>&1
}

prune_old_backend_images() {
    local image_references
    local image_reference
    local image_id
    local prune_failed="false"

    if ! image_references="$(
        docker image ls \
            --filter "reference=${IMAGE_REPOSITORY}:*" \
            --format '{{.Repository}}:{{.Tag}}'
    )"; then
        printf 'Unable to list old backend images for cleanup.\n' >&2
        return 1
    fi

    while IFS= read -r image_reference; do
        [[ -n "${image_reference}" ]] || continue
        if ! image_id="$(
            docker image inspect \
                --format '{{.Id}}' "${image_reference}"
        )"; then
            printf 'Unable to inspect backend image reference: %s\n' \
                "${image_reference}" >&2
            prune_failed="true"
            continue
        fi

        if [[ "${image_id}" == "${NEW_IMAGE_ID}" \
            || ( -n "${OLD_IMAGE}" && "${image_id}" == "${OLD_IMAGE}" ) ]]; then
            continue
        fi

        if ! docker image rm "${image_reference}" >/dev/null; then
            printf 'Unable to remove stale backend image reference: %s\n' \
                "${image_reference}" >&2
            prune_failed="true"
        fi
    done <<<"${image_references}"

    [[ "${prune_failed}" != "true" ]]
}

main() {
(($# == 1)) \
    || die "usage: ${0##*/} <lowercase-40-character-commit-sha>"

readonly DEPLOY_SHA="$1"
[[ "${DEPLOY_SHA}" =~ ^[0-9a-f]{40}$ ]] \
    || die "commit SHA must contain exactly 40 lowercase hexadecimal characters"

if ((EUID != 0)); then
    require_command sudo
    exec sudo bash "$0" "$@"
fi

readonly NEW_IMAGE="${IMAGE_REPOSITORY}:${DEPLOY_SHA}"

require_command aws
require_command curl
require_command docker
require_command flock
require_command git
require_command grep
require_command nginx
require_command sha256sum
require_command timeout

[[ -d "${REPO_DIR}/.git" ]] \
    || die "Git repository not found: ${REPO_DIR}"

exec 9>"${LOCK_FILE}"
flock --nonblock 9 \
    || die "another backend deployment is already running"

trap 'cleanup "$?"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

install -d -m 0700 "${RELEASES_DIR}" "${ENV_DIR}"

ACTIVE_PORT="$(validated_backend_upstream_port)"
if ! ACTIVE_CONTAINER="$(find_active_container "${ACTIVE_PORT}")"; then
    die "unable to determine a unique active backend container from Docker state"
fi

if [[ -n "${ACTIVE_CONTAINER}" ]]; then
    OLD_IMAGE="$(docker container inspect \
        --format '{{.Image}}' "${ACTIVE_CONTAINER}")" \
        || die "unable to inspect the active backend container"
    [[ -s "${ENV_FILE}" ]] \
        || die "rollback environment is unavailable; production was not changed"
    NEW_PORT="$(other_backend_port "${ACTIVE_PORT}")"
else
    NEW_PORT="${ACTIVE_PORT}"
fi
NEW_CONTAINER="$(slot_container_for_port "${NEW_PORT}")" \
    || die "unsupported backend deployment port: ${NEW_PORT}"
ACTIVE_WORKER="$(worker_container_for_port "${ACTIVE_PORT}")" \
    || die "unsupported active worker slot: ${ACTIVE_PORT}"
NEW_WORKER="$(worker_container_for_port "${NEW_PORT}")" \
    || die "unsupported worker slot: ${NEW_PORT}"

printf 'Creating an isolated build context for %s.\n' "${DEPLOY_SHA}"
[[ "$(git -C "${REPO_DIR}" cat-file -t "${DEPLOY_SHA}" 2>/dev/null)" == "commit" ]] \
    || die "commit is not available in the EC2 repository: ${DEPLOY_SHA}"
RELEASE_DIR="$(mktemp -d "${RELEASES_DIR}/backend.${DEPLOY_SHA}.XXXXXX")"
BACKEND_CONTEXT="${RELEASE_DIR}/backend"

if ! git -C "${REPO_DIR}" archive "${DEPLOY_SHA}" backend \
    | tar -x -C "${RELEASE_DIR}"; then
    die "unable to create the isolated backend build context"
fi
[[ -f "${BACKEND_CONTEXT}/Dockerfile" ]] \
    || die "backend Dockerfile not found in commit ${DEPLOY_SHA}"

printf 'Validating deal model artifacts in %s.\n' "${DEAL_MODEL_HOST_DIR}"
validate_deal_model_artifacts

printf 'Refreshing the backend runtime environment.\n'
if [[ -f "${ENV_FILE}" ]]; then
    OLD_ENV_FILE="$(mktemp "${ENV_DIR}/.backend.env.previous.XXXXXX")"
    install -m 0600 "${ENV_FILE}" "${OLD_ENV_FILE}"
fi

TEMP_ENV_FILE="$(mktemp "${ENV_DIR}/.backend.env.new.XXXXXX")"
chmod 0600 "${TEMP_ENV_FILE}"

if ! AWS_PAGER="" aws ssm get-parameter \
    --name "${SSM_PARAMETER}" \
    --with-decryption \
    --region "${AWS_REGION}" \
    --query 'Parameter.Value' \
    --output text >"${TEMP_ENV_FILE}"; then
    die "unable to retrieve the backend environment parameter"
fi

[[ -s "${TEMP_ENV_FILE}" ]] \
    || die "retrieved backend environment parameter is empty"
chmod 0600 "${TEMP_ENV_FILE}"
validate_runtime_environment "${TEMP_ENV_FILE}"
ENV_REPLACED="true"
mv -f -- "${TEMP_ENV_FILE}" "${ENV_FILE}" \
    || die "unable to install the refreshed backend environment"
TEMP_ENV_FILE=""

printf 'Building backend image %s.\n' "${NEW_IMAGE}"
ensure_build_disk_space
# SSM GetCommandInvocation은 표준 출력의 앞 24,000자와 표준 오류의 앞 8,000자만
# 돌려주므로 빌드 로그는 파일로 받고 실패했을 때 끝부분만 남긴다.
BUILD_LOG="${RELEASE_DIR}/build.log"
if ! build_backend_image; then
    if ! build_log_shows_disk_exhaustion "${BUILD_LOG}"; then
        tail -n 30 "${BUILD_LOG}" | tail -c 7000 >&2
        die "unable to build the backend image"
    fi

    printf 'Backend build ran out of disk space; reclaiming the Docker build cache and retrying once.\n' >&2
    prune_stale_release_dirs || true
    reclaim_build_disk_space hard
    if ! build_backend_image; then
        tail -n 30 "${BUILD_LOG}" | tail -c 7000 >&2
        die "unable to build the backend image after reclaiming disk space"
    fi
fi
IMAGE_BUILT="true"
NEW_IMAGE_ID="$(
    docker image inspect --format '{{.Id}}' "${NEW_IMAGE}"
)" || die "unable to inspect the newly built backend image"

docker rm -f "${NEW_CONTAINER}" >/dev/null 2>&1 || true
docker rm -f "${NEW_WORKER}" >/dev/null 2>&1 || true
printf 'Starting and validating backend slot %s on port %s.\n' \
    "${NEW_CONTAINER}" "${NEW_PORT}"
if ! start_production "${NEW_IMAGE}" "${NEW_CONTAINER}" "${NEW_PORT}"; then
    die "unable to start the new backend slot"
fi

if ! wait_for_backend "${NEW_PORT}"; then
    die "candidate validation failed; the production upstream was not changed"
fi
printf 'Validating the deal model in backend slot %s.\n' "${NEW_CONTAINER}"
if ! validate_deal_model_runtime "${NEW_CONTAINER}"; then
    die "deal model validation failed; the production upstream was not changed"
fi
printf 'Validating the AgentRun queue schema.\n'
if ! validate_agent_queue_schema_runtime "${NEW_CONTAINER}"; then
    die "agent queue schema validation failed; apply migrations 0017 and 0018 first"
fi

PROMOTION_STARTED="true"
if [[ -n "${ACTIVE_CONTAINER}" ]]; then
    printf 'Switching Nginx upstream from port %s to port %s.\n' \
        "${ACTIVE_PORT}" "${NEW_PORT}"
    if ! switch_backend_upstream "${ACTIVE_PORT}" "${NEW_PORT}"; then
        die "unable to switch and reload the backend Nginx upstream"
    fi
fi
printf 'Starting AgentRun worker %s after traffic promotion.\n' "${NEW_WORKER}"
if ! start_agent_worker "${NEW_IMAGE}" "${NEW_WORKER}" \
    || ! wait_for_agent_worker "${NEW_WORKER}"; then
    die "unable to start the AgentRun worker after traffic promotion"
fi

DEPLOY_SUCCEEDED="true"
PROMOTION_STARTED="false"
ENV_REPLACED="false"
UPSTREAM_CHANGE_PENDING="false"
UPSTREAM_SWITCHED="false"
if [[ -n "${OLD_UPSTREAM_FILE}" ]]; then
    rm -f -- "${OLD_UPSTREAM_FILE}" || true
    OLD_UPSTREAM_FILE=""
fi
if [[ -n "${OLD_ENV_FILE}" ]]; then
    rm -f -- "${OLD_ENV_FILE}" || true
    OLD_ENV_FILE=""
fi

if [[ -n "${ACTIVE_CONTAINER}" ]]; then
    printf 'Draining the previous backend slot for %s seconds.\n' \
        "${CONTAINER_DRAIN_SECONDS}"
    sleep "${CONTAINER_DRAIN_SECONDS}"
    if ! docker stop \
        --time "${CONTAINER_STOP_TIMEOUT_SECONDS}" \
        "${ACTIVE_CONTAINER}" >/dev/null; then
        printf 'Backend deployment succeeded, but the previous container did not stop cleanly: %s\n' \
            "${ACTIVE_CONTAINER}" >&2
    fi
    if ! docker rm "${ACTIVE_CONTAINER}" >/dev/null; then
        printf 'Backend deployment succeeded, but the previous container was not removed: %s\n' \
            "${ACTIVE_CONTAINER}" >&2
    fi
fi
if [[ -n "${ACTIVE_CONTAINER}" && "${ACTIVE_WORKER}" != "${NEW_WORKER}" ]] \
    && docker container inspect "${ACTIVE_WORKER}" >/dev/null 2>&1; then
    printf 'Stopping the previous AgentRun worker %s.\n' "${ACTIVE_WORKER}"
    if ! docker stop \
        --time "${CONTAINER_STOP_TIMEOUT_SECONDS}" \
        "${ACTIVE_WORKER}" >/dev/null; then
        printf 'Backend deployment succeeded, but the previous worker did not stop cleanly: %s\n' \
            "${ACTIVE_WORKER}" >&2
    fi
    docker rm "${ACTIVE_WORKER}" >/dev/null 2>&1 || true
fi

if ! prune_old_backend_images; then
    printf 'Backend deployment succeeded, but stale image cleanup was incomplete.\n' >&2
fi

printf 'Backend deployment completed successfully.\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
