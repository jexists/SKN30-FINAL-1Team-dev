"""Supabase Storage 호출 경계.

업로드와 서명 URL 발급 두 가지만 둔다. 저장소를 바꾸면 이 모듈만 교체한다.

secret 키는 RLS 를 우회하므로 서버 프로세스 안에서만 쓰고 응답이나
오류 메시지에 남기지 않는다. storage_key 도 클라이언트에 내보내지 않는다.
"""

from uuid import UUID, uuid4

import httpx

from app.core.config import settings


class StorageError(Exception):
    """저장소 호출이 실패했다. 메시지에 키나 내부 주소를 담지 않는다."""


class StorageNotConfigured(StorageError):
    """secret 키나 버킷 이름이 없다."""


def build_storage_key(team_id: UUID, extension: str) -> str:
    """저장 경로는 서버가 만든다. 원본 파일명을 경로에 쓰지 않는다."""
    return f"{team_id}/{uuid4()}{extension}"


def _endpoint(path: str) -> str:
    return f"{settings.supabase_project_url}/storage/v1/{path}"


def _headers() -> dict[str, str]:
    key = settings.supabase_secret_key.get_secret_value()
    return {"Authorization": f"Bearer {key}", "apikey": key}


def _require_config() -> None:
    if not settings.storage_configured:
        raise StorageNotConfigured("storage_not_configured")


async def upload(*, storage_key: str, content: bytes, media_type: str) -> None:
    _require_config()
    url = _endpoint(f"object/{settings.supabase_storage_bucket}/{storage_key}")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={**_headers(), "Content-Type": media_type, "x-upsert": "false"},
                content=content,
            )
    except httpx.HTTPError as error:
        raise StorageError(f"storage_request_failed:{type(error).__name__}") from error
    if response.status_code >= 400:
        raise StorageError(f"storage_upload_failed:{response.status_code}")


async def signed_url(*, storage_key: str, expires_in: int = 60) -> str:
    """짧게 사는 다운로드 주소. 매 요청마다 권한을 확인한 뒤에만 부른다."""
    _require_config()
    url = _endpoint(f"object/sign/{settings.supabase_storage_bucket}/{storage_key}")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=_headers(), json={"expiresIn": expires_in})
    except httpx.HTTPError as error:
        raise StorageError(f"storage_request_failed:{type(error).__name__}") from error
    if response.status_code >= 400:
        raise StorageError(f"storage_sign_failed:{response.status_code}")

    try:
        signed = response.json()["signedURL"]
    except (ValueError, KeyError, TypeError) as error:
        raise StorageError("storage_sign_response_invalid") from error
    return f"{settings.supabase_project_url}/storage/v1{signed}"


async def download(*, storage_key: str) -> bytes:
    """서버 내부 문서 처리용 원본 다운로드. storage_key 는 응답에 노출하지 않는다."""
    _require_config()
    url = _endpoint(f"object/{settings.supabase_storage_bucket}/{storage_key}")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, headers=_headers())
    except httpx.HTTPError as error:
        raise StorageError(f"storage_request_failed:{type(error).__name__}") from error
    if response.status_code >= 400:
        raise StorageError(f"storage_download_failed:{response.status_code}")
    if len(response.content) > settings.upload_max_bytes:
        raise StorageError("storage_download_too_large")
    return response.content


async def remove(*, storage_key: str) -> None:
    """업로드 뒤 DB 기록이 실패했을 때 되돌리기 위해 쓴다."""
    _require_config()
    url = _endpoint(f"object/{settings.supabase_storage_bucket}/{storage_key}")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.delete(url, headers=_headers())
    except httpx.HTTPError:
        # 정리 실패가 원래 오류를 덮지 않게 한다. 고아 객체는 남을 수 있다.
        return
