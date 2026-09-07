import pytest

from app.services.upload_guard import (
    UploadRejected,
    check_report_attachment_upload,
    check_upload,
)


@pytest.mark.parametrize(
    ("file_name", "media_type", "content", "expected_media_type"),
    [
        ("proposal.html", "text/html", "<h1>제안서</h1>".encode(), "text/html"),
        ("proposal.txt", "text/plain", "계약기간: 1년".encode(), "text/plain"),
        (
            "proposal.md",
            "text/markdown",
            "## 지급 조건\n\n검수 후 지급".encode(),
            "text/markdown",
        ),
        (
            "contract.hwp",
            "application/octet-stream",
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"hwp",
            "application/x-hwp",
        ),
    ],
)
def test_document_upload_accepts_supported_text_and_hwp_formats(
    file_name, media_type, content, expected_media_type
):
    allowed = check_upload(
        file_name=file_name,
        declared_media_type=media_type,
        content=content,
    )

    assert allowed.extension == f".{file_name.rsplit('.', 1)[1]}"
    assert allowed.media_type == expected_media_type


def test_html_upload_rejects_binary_content_before_extraction():
    with pytest.raises(UploadRejected, match="file_signature_mismatch"):
        check_upload(
            file_name="proposal.html",
            declared_media_type="text/html",
            content=b"<html>\x00<script>alert(1)</script>",
        )


@pytest.mark.parametrize(
    ("file_name", "media_type", "content", "expected_media_type"),
    [
        ("meeting.wav", "audio/wav", b"RIFF\x24\x00\x00\x00WAVE", "audio/wav"),
        ("photo.png", "image/png", b"\x89PNG\r\n\x1a\nbody", "image/png"),
        ("proposal.pdf", "application/pdf", b"%PDF-1.7\n", "application/pdf"),
    ],
)
def test_report_attachment_accepts_only_shared_report_media(
    file_name, media_type, content, expected_media_type
):
    allowed = check_report_attachment_upload(
        file_name=file_name,
        declared_media_type=media_type,
        content=content,
    )

    assert allowed.media_type == expected_media_type


@pytest.mark.parametrize(
    ("file_name", "content", "expected_media_type"),
    [
        ("meeting.wav", b"RIFF\x24\x00\x00\x00WAVE", "audio/wav"),
        ("photo.png", b"\x89PNG\r\n\x1a\nbody", "image/png"),
        ("proposal.pdf", b"%PDF-1.7\n", "application/pdf"),
    ],
)
def test_report_attachment_treats_octet_stream_as_undeclared_mime(
    file_name, content, expected_media_type
):
    allowed = check_report_attachment_upload(
        file_name=file_name,
        declared_media_type="application/octet-stream",
        content=content,
    )

    assert allowed.media_type == expected_media_type


def test_octet_stream_normalization_is_report_attachment_only():
    with pytest.raises(UploadRejected, match="media_type_mismatch"):
        check_upload(
            file_name="proposal.pdf",
            declared_media_type="application/octet-stream",
            content=b"%PDF-1.7\n",
        )


def test_report_attachment_rejects_other_document_formats():
    with pytest.raises(UploadRejected, match="unsupported_file_extension"):
        check_report_attachment_upload(
            file_name="proposal.docx",
            declared_media_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            content=b"PK\x03\x04",
        )


def test_report_attachment_rejects_file_name_too_long():
    with pytest.raises(UploadRejected, match="invalid_file_name"):
        check_report_attachment_upload(
            file_name=f"{'a' * 251}.pdf",
            declared_media_type="application/pdf",
            content=b"%PDF-1.7\n",
        )
