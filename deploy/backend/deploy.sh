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

readonly IMAGE_REPOSITORY="salesluv-backend"
readonly PRODUCTION_CONTAINER="salesluv-backend"
readonly CANDIDATE_CONTAINER="salesluv-backend-candidate"
readonly PRODUCTION_PORT="8000"
readonly CANDIDATE_PORT="18000"

readonly HEALTH_ATTEMPTS="30"
readonly HEALTH_DELAY_SECONDS="2"
readonly HEALTH_TIMEOUT_SECONDS="5"

TEMP_ENV_FILE=""
OLD_ENV_FILE=""
RELEASE_DIR=""
BACKEND_CONTEXT=""
OLD_IMAGE=""
OLD_CONTAINER_ID=""
NEW_IMAGE_ID=""
ENV_REPLACED="false"
IMAGE_BUILT="false"
PROMOTION_STARTED="false"
ROLLBACK_ATTEMPTED="false"
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

# 키가 정확히 한 번만 나올 때 그 값을 출력한다. 없거나 중복이면 아무것도 출력하지 않는다.
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
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
            if (key != expected_key) {
                next
            }

            value = substr(line, separator + 1)

            matches++
            matched_value = value
        }
        END {
            if (matches == 1) {
                print matched_value
            }
        }
    ' "${dotenv_file}"
}

validate_runtime_environment() {
    local dotenv_file="$1"
    local required_key
    local value

    for required_key in \
        APP_ENV \
        DEBUG \
        CORS_ORIGINS \
        DATABASE_URL \
        SUPABASE_PUBLISHABLE_KEY; do
        value="$(dotenv_value "${dotenv_file}" "${required_key}")"
        [[ -n "${value}" ]] \
            || die "required environment key is missing or empty: ${required_key}"

        case "${required_key}" in
            APP_ENV)
                [[ "${value}" == "production" ]] || die "APP_ENV must be production"
                ;;
            DEBUG)
                [[ "${value}" == "false" ]] || die "DEBUG must be false"
                ;;
        esac
    done
}

cleanup() {
    local exit_status="$1"

    trap - EXIT
    trap '' HUP INT TERM
    set +e

    if [[ "${DEPLOY_SUCCEEDED}" != "true" ]]; then
        if [[ "${PROMOTION_STARTED}" == "true" \
            && "${ROLLBACK_ATTEMPTED}" != "true" ]]; then
            if ! rollback_production "${OLD_IMAGE}"; then
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
    if [[ -n "${OLD_ENV_FILE}" && "${ENV_REPLACED}" != "true" ]]; then
        rm -f -- "${OLD_ENV_FILE}" >/dev/null 2>&1 || true
        OLD_ENV_FILE=""
    elif [[ -n "${OLD_ENV_FILE}" ]]; then
        printf 'Previous environment backup retained at: %s\n' \
            "${OLD_ENV_FILE}" >&2
    fi

    docker rm -f "${CANDIDATE_CONTAINER}" >/dev/null 2>&1 || true
    if [[ "${IMAGE_BUILT}" == "true" \
        && "${DEPLOY_SUCCEEDED}" != "true" ]]; then
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

start_candidate() {
    docker run --detach \
        --name "${CANDIDATE_CONTAINER}" \
        --env-file "${ENV_FILE}" \
        --publish "127.0.0.1:${CANDIDATE_PORT}:8000" \
        "${NEW_IMAGE}" >/dev/null
}

start_production() {
    local image="$1"

    docker run --detach \
        --name "${PRODUCTION_CONTAINER}" \
        --restart unless-stopped \
        --log-driver json-file \
        --log-opt max-size=10m \
        --log-opt max-file=3 \
        --env-file "${ENV_FILE}" \
        --publish "127.0.0.1:${PRODUCTION_PORT}:8000" \
        "${image}" >/dev/null
}

rollback_production() {
    local rollback_image="$1"
    local current_container_id=""

    ROLLBACK_ATTEMPTED="true"
    printf 'Production replacement was interrupted; starting rollback.\n' >&2

    if ! restore_previous_environment; then
        printf 'Rollback could not restore the previous environment file.\n' >&2
        if [[ -n "${OLD_ENV_FILE}" ]]; then
            printf 'Previous environment backup retained at: %s\n' \
                "${OLD_ENV_FILE}" >&2
        fi
        return 1
    fi

    if docker container inspect "${PRODUCTION_CONTAINER}" >/dev/null 2>&1; then
        if ! current_container_id="$(
            docker container inspect \
                --format '{{.Id}}' "${PRODUCTION_CONTAINER}"
        )"; then
            printf 'Rollback could not inspect the production container.\n' >&2
            return 1
        fi

        if [[ -n "${OLD_CONTAINER_ID}" \
            && "${current_container_id}" == "${OLD_CONTAINER_ID}" ]] \
            && wait_for_backend "${PRODUCTION_PORT}"; then
            PROMOTION_STARTED="false"
            printf 'Production remained available; rollback is complete.\n' >&2
            return 0
        fi

        if ! docker rm -f "${PRODUCTION_CONTAINER}" >/dev/null; then
            printf 'Rollback could not remove the replacement container.\n' >&2
            return 1
        fi
    fi

    if [[ -z "${rollback_image}" ]]; then
        printf 'No previous production image is available to restore.\n' >&2
        PROMOTION_STARTED="false"
        return 0
    fi

    if [[ ! -s "${ENV_FILE}" ]]; then
        printf 'No previous environment file is available for rollback.\n' >&2
        return 1
    fi

    if ! start_production "${rollback_image}"; then
        printf 'Rollback failed to start the previous production image.\n' >&2
        return 1
    fi

    if ! wait_for_backend "${PRODUCTION_PORT}"; then
        printf 'Previous production image started, but rollback health checks failed.\n' >&2
        return 1
    fi

    PROMOTION_STARTED="false"
    printf 'Previous production image and environment restored.\n' >&2
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
# SSM GetCommandInvocation은 표준 출력의 앞 24,000자와 표준 오류의 앞 8,000자만
# 돌려주므로 빌드 로그는 파일로 받고 실패했을 때 끝부분만 남긴다.
BUILD_LOG="${RELEASE_DIR}/build.log"
if ! DOCKER_BUILDKIT=1 docker build --progress=plain \
    --tag "${NEW_IMAGE}" "${BACKEND_CONTEXT}" >"${BUILD_LOG}" 2>&1; then
    tail -n 30 "${BUILD_LOG}" | tail -c 7000 >&2
    die "unable to build the backend image"
fi
IMAGE_BUILT="true"
NEW_IMAGE_ID="$(
    docker image inspect --format '{{.Id}}' "${NEW_IMAGE}"
)" || die "unable to inspect the newly built backend image"

docker rm -f "${CANDIDATE_CONTAINER}" >/dev/null 2>&1 || true
printf 'Starting and validating the candidate container.\n'
start_candidate

if ! wait_for_backend "${CANDIDATE_PORT}"; then
    die "candidate validation failed; the production container was not changed"
fi
docker rm -f "${CANDIDATE_CONTAINER}" >/dev/null

if docker container inspect "${PRODUCTION_CONTAINER}" >/dev/null 2>&1; then
    OLD_CONTAINER_ID="$(
        docker container inspect \
            --format '{{.Id}}' "${PRODUCTION_CONTAINER}"
    )"
    OLD_IMAGE="$(
        docker container inspect \
            --format '{{.Image}}' "${PRODUCTION_CONTAINER}"
    )"
fi

if [[ -n "${OLD_IMAGE}" \
    && ( ! -f "${OLD_ENV_FILE}" || ! -s "${OLD_ENV_FILE}" ) ]]; then
    die "rollback environment is unavailable; production was not changed"
fi

PROMOTION_STARTED="true"
if [[ -n "${OLD_IMAGE}" ]]; then
    if ! docker rm -f "${PRODUCTION_CONTAINER}" >/dev/null; then
        die "unable to remove the current production container"
    fi
fi

printf 'Promoting the validated image to production.\n'
if ! start_production "${NEW_IMAGE}"; then
    die "unable to start the validated production image"
fi

if ! wait_for_backend "${PRODUCTION_PORT}"; then
    die "production health checks failed"
fi

DEPLOY_SUCCEEDED="true"
PROMOTION_STARTED="false"
ENV_REPLACED="false"
if [[ -n "${OLD_ENV_FILE}" ]]; then
    rm -f -- "${OLD_ENV_FILE}" || true
    OLD_ENV_FILE=""
fi

if ! prune_old_backend_images; then
    printf 'Backend deployment succeeded, but stale image cleanup was incomplete.\n' >&2
fi

printf 'Backend deployment completed successfully.\n'
