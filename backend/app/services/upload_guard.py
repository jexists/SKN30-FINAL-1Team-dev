"""업로드 파일 검증.

확장자, 선언된 MIME, 실제 파일 signature 를 함께 본다. 셋 중 하나라도
어긋나면 거절한다. 단순화를 이유로 생략하지 않는다.
"""

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


# 멀티에이전트 운영 플로우의 자료실 입력이 PDF·PPTX·DOCX 다. HTML 은 규약 13절에 따라
# 인라인 실행 위험이 있어 받지 않는다.
_ALLOWED: tuple[AllowedType, ...] = (
    AllowedType(".pdf", _PDF, (b"%PDF-",)),
    AllowedType(".docx", _DOCX, (b"PK\x03\x04",)),
    AllowedType(".pptx", _PPTX, (b"PK\x03\x04",)),
)

_BY_EXTENSION = {allowed.extension: allowed for allowed in _ALLOWED}

ALLOWED_EXTENSIONS = tuple(sorted(_BY_EXTENSION))


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
        if declared and declared != allowed.media_type:
            raise UploadRejected("media_type_mismatch", 415)

    if not content:
        raise UploadRejected("empty_file", 422)

    if not any(content.startswith(magic) for magic in allowed.magic):
        raise UploadRejected("file_signature_mismatch", 415)

    return allowed


def check_size(byte_size: int, limit: int) -> None:
    if byte_size <= 0:
        raise UploadRejected("empty_file", 422)
    if byte_size > limit:
        raise UploadRejected("file_too_large", 413)
