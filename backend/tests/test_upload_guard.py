import pytest

from app.services.upload_guard import (
    ALLOWED_EXTENSIONS,
    UploadRejected,
    check_size,
    check_upload,
)

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 8
DOCX = b"PK\x03\x04" + b"\x00" * 8
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_accepts_matching_extension_mime_and_signature():
    result = check_upload(
        file_name="제안서.pdf", declared_media_type="application/pdf", content=PDF
    )
    assert result.media_type == "application/pdf"

    assert (
        check_upload(file_name="c.docx", declared_media_type=DOCX_TYPE, content=DOCX).extension
        == ".docx"
    )
    # charset 이 붙어도 앞부분만 본다.
    assert check_upload(
        file_name="d.pdf", declared_media_type="application/pdf; charset=binary", content=PDF
    )


def test_rejects_disguised_extension():
    """확장자만 바꾼 실행 파일은 signature 에서 걸린다."""
    with pytest.raises(UploadRejected) as caught:
        check_upload(
            file_name="악성.pdf", declared_media_type="application/pdf", content=b"MZ\x90\x00"
        )
    assert caught.value.detail == "file_signature_mismatch"
    assert caught.value.status_code == 415


def test_rejects_mime_that_contradicts_extension():
    with pytest.raises(UploadRejected) as caught:
        check_upload(file_name="a.pdf", declared_media_type="image/png", content=PDF)
    assert caught.value.detail == "media_type_mismatch"
    assert caught.value.status_code == 415


def test_rejects_unsupported_and_executable_types():
    # 유스케이스에 없는 이미지·스프레드시트도 받지 않는다.
    for name in ("a.exe", "b.sh", "c.zip", "d.html", "e.svg", "noextension", "f.png", "g.xlsx"):
        with pytest.raises(UploadRejected) as caught:
            check_upload(file_name=name, declared_media_type=None, content=PDF)
        assert caught.value.detail == "unsupported_file_extension"
        assert caught.value.status_code == 415

    assert ".exe" not in ALLOWED_EXTENSIONS
    assert ".zip" not in ALLOWED_EXTENSIONS
    assert ".html" not in ALLOWED_EXTENSIONS


def test_rejects_path_traversal_in_file_name():
    for name in ("../../etc/passwd.pdf", "a/b.pdf", "a\\b.pdf", "..", "."):
        with pytest.raises(UploadRejected) as caught:
            check_upload(file_name=name, declared_media_type=None, content=PDF)
        assert caught.value.detail in {"invalid_file_name", "unsupported_file_extension"}


def test_rejects_empty_content():
    with pytest.raises(UploadRejected) as caught:
        check_upload(file_name="a.pdf", declared_media_type=None, content=b"")
    assert caught.value.detail == "empty_file"
    assert caught.value.status_code == 422


def test_size_limit_uses_413():
    check_size(10, 100)
    with pytest.raises(UploadRejected) as caught:
        check_size(101, 100)
    assert caught.value.detail == "file_too_large"
    assert caught.value.status_code == 413

    with pytest.raises(UploadRejected) as caught:
        check_size(0, 100)
    assert caught.value.detail == "empty_file"
