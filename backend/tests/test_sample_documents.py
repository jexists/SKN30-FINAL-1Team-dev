from pathlib import Path

import pytest

from app.core.config import settings
from app.services import document_extraction
from app.services.document_extraction import ExtractionError, extract_document

SAMPLE_DIR = Path(__file__).parents[2] / "data" / "sanitized_docs"


def test_checked_in_sample_docx_extracts_paragraphs_and_tables():
    samples = list(SAMPLE_DIR.glob("*카드결제*.docx"))
    if not samples:
        pytest.skip("sample_docx_not_available")

    sample = samples[0]
    result = extract_document(
        file_name=sample.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content=sample.read_bytes(),
    )

    assert result.payload["source_type"] == "docx"
    assert len(result.plain_text) > 100
    assert len(result.payload["pages"]) == 1
    assert "|" in result.markdown


def test_checked_in_sample_text_pdf_extracts_without_ocr():
    samples = list(SAMPLE_DIR.glob("*.pdf"))
    if not samples:
        pytest.skip("sample_pdf_not_available")

    extracted = []
    for sample in samples:
        try:
            result = extract_document(
                file_name=sample.name,
                media_type="application/pdf",
                content=sample.read_bytes(),
            )
        except ExtractionError:
            continue
        extracted.append(result)

    assert extracted
    assert any(len(result.plain_text) > 100 for result in extracted)
    assert all(result.payload["pages"] for result in extracted)


def test_checked_in_scanned_pdf_stops_until_ocr_is_configured():
    samples = list(SAMPLE_DIR.glob("*사업자등록증*.pdf"))
    if not samples:
        pytest.skip("sample_scanned_pdf_not_available")

    with pytest.raises(ExtractionError, match="ocr_required"):
        sample = samples[0]
        extract_document(
            file_name=sample.name,
            media_type="application/pdf",
            content=sample.read_bytes(),
        )


def test_hwp_uses_soffice_when_hwp5txt_is_unavailable(monkeypatch):
    def _run(command, **_kwargs):
        outdir = Path(command[command.index("--outdir") + 1])
        (outdir / "document.txt").write_text("HWP 테스트 본문", encoding="utf-8")
        return type("Completed", (), {"returncode": 0})()

    def _which(name):
        return "/usr/bin/soffice" if name == "soffice" else None

    monkeypatch.setattr(document_extraction.shutil, "which", _which)
    monkeypatch.setattr(document_extraction.subprocess, "run", _run)
    monkeypatch.setattr(settings, "soffice_path", "")

    result = document_extraction._hwp(b"fake-hwp")

    assert result.payload["source_type"] == "hwp"
    assert result.plain_text == "HWP 테스트 본문"
