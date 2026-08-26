from app.core.config import Settings
from app.services import ocr
from app.services.ocr import _azure_result, _runpod_result, _runpod_runsync_url


def test_azure_result_preserves_page_markdown_and_page_numbers():
    result = _azure_result(
        {
            "analyzeResult": {
                "pages": [
                    {"pageNumber": 1, "lines": [{"content": "계약 조건"}]},
                    {"pageNumber": 2, "lines": [{"content": "지급 조건"}]},
                ]
            }
        },
        file_name="contract.pdf",
    )

    pages = result.payload["pages"]
    assert [page["page_number"] for page in pages] == [1, 2]
    assert "계약 조건" in pages[0]["markdown"]
    assert "지급 조건" in pages[1]["markdown"]
    assert result.payload["ocr_provider"] == "azure_document_intelligence"


def test_runpod_settings_require_api_url_and_key():
    settings = Settings(
        app_env="test",
        ocr_provider="runpod",
        ocr_api_url="https://api.runpod.ai/v2/test-endpoint",
        ocr_api_key="runpod-test-key",
    )

    assert settings.ocr_configured is True


def test_runpod_template_url_is_not_treated_as_configured():
    settings = Settings(
        app_env="test",
        ocr_provider="runpod",
        ocr_api_url="https://api.runpod.ai/v2/{ENDPOINT_ID}",
        ocr_api_key="runpod-test-key",
    )

    assert settings.ocr_configured is False


def test_runpod_runsync_url_adds_wait_parameter():
    assert (
        _runpod_runsync_url("https://api.runpod.ai/v2/endpoint", 120)
        == "https://api.runpod.ai/v2/endpoint/runsync?wait=120000"
    )


def test_runpod_result_preserves_page_markdown_and_provenance():
    result = _runpod_result(
        {
            "id": "job-123",
            "status": "COMPLETED",
            "output": {
                "pages": [
                    {"page_number": 1, "markdown": "## 계약기간\n12개월"},
                    {"page_number": 2, "markdown": "## 납기\n30일"},
                ]
            },
        },
        file_name="contract.pdf",
    )

    assert [page["page_number"] for page in result.payload["pages"]] == [1, 2]
    assert "계약기간" in result.markdown
    assert result.payload["ocr_provider"] == "runpod"
    assert result.payload["runpod_job_id"] == "job-123"


def test_runpod_result_accepts_line_based_worker_output():
    result = _runpod_result(
        {
            "status": "COMPLETED",
            "output": {
                "pages": [
                    {
                        "page_number": 1,
                        "lines": [{"content": "대표이사 홍길동", "confidence": 0.99}],
                    }
                ]
            },
        },
        file_name="business-card.png",
    )

    assert "대표이사 홍길동" in result.plain_text
    assert result.payload["source_type"] == "runpod_ocr"


def test_pdf_inspector_model_directory_uses_configured_path(monkeypatch):
    monkeypatch.setattr(ocr.settings, "pdf_inspector_model_directory", "~/salesluv-models")

    assert ocr._pdf_inspector_model_directory().endswith("/salesluv-models")


def test_pdf_inspector_model_directory_defaults_to_temp(monkeypatch):
    monkeypatch.setattr(ocr.settings, "pdf_inspector_model_directory", "")

    assert ocr._pdf_inspector_model_directory().endswith("salesluv-pdf-inspector-models")


def test_pdf_inspector_model_directory_finds_nested_downloaded_artifacts(tmp_path, monkeypatch):
    nested = tmp_path / "pp-ocrv6-small" / "oar-ocr-v0.7.0"
    nested.mkdir(parents=True)
    (nested / "pp-ocrv6_small_det.onnx").write_bytes(b"model")
    monkeypatch.setattr(ocr.settings, "pdf_inspector_model_directory", str(tmp_path))

    assert ocr._pdf_inspector_model_directory() == str(nested)


def test_pdf_inspector_model_cache_sets_library_environment(monkeypatch):
    monkeypatch.delenv("PDF_INSPECTOR_MODEL_CACHE", raising=False)
    monkeypatch.setattr(ocr.settings, "pdf_inspector_model_directory", "/tmp/salesluv-models")

    ocr._configure_pdf_inspector_model_cache()

    assert ocr.os.environ["PDF_INSPECTOR_MODEL_CACHE"] == "/tmp/salesluv-models"


def test_pdf_inspector_uses_local_model_directory_and_offline_mode(monkeypatch):
    calls = []

    class _Inspector:
        @staticmethod
        def process_pdf_with_ocr_bytes(content, **kwargs):
            calls.append((content, kwargs))
            return {"pages": [{"page_number": 1, "markdown": "본문"}]}

    monkeypatch.setitem(__import__("sys").modules, "pdf_inspector", _Inspector)
    monkeypatch.setattr(ocr, "_configure_pdfium", lambda: None)
    monkeypatch.setattr(ocr, "_configure_onnxruntime", lambda: None)
    monkeypatch.setattr(ocr, "_configure_pdf_inspector_model_cache", lambda: None)
    monkeypatch.setattr(ocr.settings, "pdf_inspector_model_directory", "/tmp/pdf-models")

    result = ocr._local_pdf(content=b"pdf", file_name="scan.pdf")

    assert result.plain_text == "본문"
    assert calls == [
        (
            b"pdf",
            {"model_directory": "/tmp/pdf-models", "offline": True},
        )
    ]


def test_paddlex_cache_sets_library_environment(monkeypatch):
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    monkeypatch.delenv("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", raising=False)
    monkeypatch.setattr(ocr.settings, "paddlex_cache_home", "/tmp/salesluv-paddlex")

    ocr._configure_paddlex_cache()

    assert ocr.os.environ["PADDLE_PDX_CACHE_HOME"] == "/tmp/salesluv-paddlex"
    assert ocr.os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] == "True"
