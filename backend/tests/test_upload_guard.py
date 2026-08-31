import pytest

from app.services.upload_guard import UploadRejected, check_upload


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
