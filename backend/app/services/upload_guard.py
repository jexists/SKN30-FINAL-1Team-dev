"""업로드 파일 검증.

확장자, 선언된 MIME, 실제 파일 signature 를 함께 본다. 셋 중 하나라도
어긋나면 거절한다. 단순화를 이유로 생략하지 않는다.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

# 허용 형식만 둔다. 실행 가능한 형식과 압축 파일은 넣지 않는다.
# (확장자, 선언 MIME 집합, signature 검사 함수)
_PDF = "application/pdf"
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class UploadRejected(Exception):
    """업로드를 받을 수 없다. detail 은 API 가 그대로 쓰는 안정적인 코드다."""

    def __init__(self, detail: str, status_code: int):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class AllowedType:
    extension: str
    media_type: str
    # OOXML 은 전부 zip 이라 signature 만으로는 서로 구분되지 않는다.
    magic: tuple[bytes, ...]
    declared_media_types: frozenset[str] | None = None
    has_signature: Callable[[bytes], bool] | None = None


@dataclass(frozen=True)
class AllowedMediaType:
    """확장자 하나에 선언 MIME 이 여럿 붙는 형식. 음성과 이미지가 이 모양이다."""

    extension: str
    media_type: str
    declared_media_types: frozenset[str]
    has_signature: Callable[[bytes], bool]


# HTML은 저장 후 브라우저에서 실행하지 않고 document_extraction에서 script/style을 제거한
# 텍스트만 사용한다. HWP는 hwp5txt 또는 LibreOffice soffice가 설치된 경우 실제 추출된다.
_ALLOWED: tuple[AllowedType, ...] = (
    AllowedType(".pdf", _PDF, (b"%PDF-",)),
    AllowedType(".docx", _DOCX, (b"PK\x03\x04",)),
    AllowedType(".pptx", _PPTX, (b"PK\x03\x04",)),
    AllowedType(
        ".html",
        "text/html",
        (),
        frozenset(("text/html",)),
        lambda content: _is_html(content),
    ),
    AllowedType(
        ".htm",
        "text/html",
        (),
        frozenset(("text/html",)),
        lambda content: _is_html(content),
    ),
    AllowedType(
        ".txt",
        "text/plain",
        (),
        frozenset(("text/plain",)),
        lambda content: _is_text(content),
    ),
    AllowedType(
        ".md",
        "text/markdown",
        (),
        frozenset(("text/markdown", "text/plain")),
        lambda content: _is_text(content),
    ),
    AllowedType(
        ".markdown",
        "text/markdown",
        (),
        frozenset(("text/markdown", "text/plain")),
        lambda content: _is_text(content),
    ),
    AllowedType(
        ".hwp",
        "application/x-hwp",
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
        frozenset(("application/x-hwp", "application/haansofthwp", "application/octet-stream")),
    ),
)

_BY_EXTENSION = {allowed.extension: allowed for allowed in _ALLOWED}

ALLOWED_EXTENSIONS = tuple(sorted(_BY_EXTENSION))


def _is_text(content: bytes) -> bool:
    return b"\x00" not in content


def _is_html(content: bytes) -> bool:
    if not _is_text(content):
        return False
    text = content.decode("utf-8", errors="replace").lstrip().lower()
    return bool(re.search(r"<\s*(?:!doctype\b|html\b|head\b|body\b|[a-z][^>]*>)", text))


def _is_mpeg_audio(content: bytes) -> bool:
    if content.startswith(b"ID3"):
        return True
    return (
        len(content) >= 2
        and content[0] == 0xFF
        and content[1] & 0xE0 == 0xE0
        and content[1] & 0x06 != 0
    )


def _is_m4a(content: bytes) -> bool:
    return len(content) >= 12 and content[4:8] == b"ftyp"


def _is_wav(content: bytes) -> bool:
    return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WAVE"


def _is_webm(content: bytes) -> bool:
    return content.startswith(b"\x1aE\xdf\xa3")


_AUDIO_ALLOWED: tuple[AllowedMediaType, ...] = (
    AllowedMediaType(
        ".mp3",
        "audio/mpeg",
        frozenset(("audio/mpeg", "audio/mp3")),
        _is_mpeg_audio,
    ),
    AllowedMediaType(
        ".m4a",
        "audio/mp4",
        frozenset(("audio/mp4", "audio/m4a", "audio/x-m4a")),
        _is_m4a,
    ),
    AllowedMediaType(
        ".wav",
        "audio/wav",
        frozenset(("audio/wav", "audio/wave", "audio/x-wav")),
        _is_wav,
    ),
    AllowedMediaType(
        ".webm",
        "audio/webm",
        frozenset(("audio/webm",)),
        _is_webm,
    ),
)
_AUDIO_BY_EXTENSION = {allowed.extension: allowed for allowed in _AUDIO_ALLOWED}


def _is_png(content: bytes) -> bool:
    return content.startswith(b"\x89PNG\r\n\x1a\n")


def _is_jpeg(content: bytes) -> bool:
    return content.startswith(b"\xff\xd8\xff")


def _is_webp(content: bytes) -> bool:
    return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP"


# 상품 사진이 쓴다. 자료실(_ALLOWED)과 섞지 않는다. 브라우저가 그대로 그리는 형식만 두고
# SVG 는 스크립트를 품을 수 있어 받지 않는다.
_IMAGE_ALLOWED: tuple[AllowedMediaType, ...] = (
    AllowedMediaType(".png", "image/png", frozenset(("image/png",)), _is_png),
    AllowedMediaType(".jpg", "image/jpeg", frozenset(("image/jpeg", "image/jpg")), _is_jpeg),
    AllowedMediaType(".jpeg", "image/jpeg", frozenset(("image/jpeg", "image/jpg")), _is_jpeg),
    AllowedMediaType(".webp", "image/webp", frozenset(("image/webp",)), _is_webp),
)
_IMAGE_BY_EXTENSION = {allowed.extension: allowed for allowed in _IMAGE_ALLOWED}

ALLOWED_IMAGE_EXTENSIONS = tuple(sorted(_IMAGE_BY_EXTENSION))


def _extension_of(file_name: str) -> str:
    name = file_name.strip().lower()
    dot = name.rfind(".")
    return name[dot:] if dot > 0 else ""


def check_upload(*, file_name: str, declared_media_type: str | None, content: bytes) -> AllowedType:
    """통과하면 확정된 형식을 돌려준다. 실패하면 UploadRejected 를 던진다."""
    name = file_name.strip()
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise UploadRejected("invalid_file_name", 422)

    allowed = _BY_EXTENSION.get(_extension_of(name))
    if allowed is None:
        raise UploadRejected("unsupported_file_extension", 415)

    # 선언 MIME 은 클라이언트 값이라 신뢰하지 않고 확장자와 일치할 때만 받는다.
    if declared_media_type is not None:
        declared = declared_media_type.split(";")[0].strip().lower()
        declared_media_types = allowed.declared_media_types or frozenset((allowed.media_type,))
        if declared and declared not in declared_media_types:
            raise UploadRejected("media_type_mismatch", 415)

    if not content:
        raise UploadRejected("empty_file", 422)

    if allowed.has_signature is not None:
        signature_matches = allowed.has_signature(content)
    else:
        signature_matches = any(content.startswith(magic) for magic in allowed.magic)
    if not signature_matches:
        raise UploadRejected("file_signature_mismatch", 415)

    return allowed


def _check_media_upload(
    by_extension: dict[str, AllowedMediaType],
    *,
    file_name: str,
    declared_media_type: str | None,
    content: bytes,
) -> AllowedMediaType:
    name = file_name.strip()
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise UploadRejected("invalid_file_name", 422)

    allowed = by_extension.get(_extension_of(name))
    if allowed is None:
        raise UploadRejected("unsupported_file_extension", 415)

    if declared_media_type is not None:
        declared = declared_media_type.split(";")[0].strip().lower()
        if declared and declared not in allowed.declared_media_types:
            raise UploadRejected("media_type_mismatch", 415)

    if not content:
        raise UploadRejected("empty_file", 422)
    if not allowed.has_signature(content):
        raise UploadRejected("file_signature_mismatch", 415)
    return allowed


def check_audio_upload(
    *, file_name: str, declared_media_type: str | None, content: bytes
) -> AllowedMediaType:
    """STT가 받을 음성인지 확장자·MIME·signature를 함께 확인한다."""
    return _check_media_upload(
        _AUDIO_BY_EXTENSION,
        file_name=file_name,
        declared_media_type=declared_media_type,
        content=content,
    )


def check_image_upload(
    *, file_name: str, declared_media_type: str | None, content: bytes
) -> AllowedMediaType:
    """상품 사진으로 받을 이미지인지 확장자·MIME·signature를 함께 확인한다."""
    return _check_media_upload(
        _IMAGE_BY_EXTENSION,
        file_name=file_name,
        declared_media_type=declared_media_type,
        content=content,
    )


def check_size(byte_size: int, limit: int) -> None:
    if byte_size <= 0:
        raise UploadRejected("empty_file", 422)
    if byte_size > limit:
        raise UploadRejected("file_too_large", 413)
