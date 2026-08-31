import base64
import time

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services import ocr
from app.services.ocr import (
    _azure_result,
    _runpod_result,
    _runpod_runsync_url,
    _runpod_status_url,
)


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


def test_runpod_status_url_accepts_endpoint_or_runsync_url():
    assert (
        _runpod_status_url("https://api.runpod.ai/v2/endpoint", "job/123")
        == "https://api.runpod.ai/v2/endpoint/status/job%2F123"
    )
    assert (
        _runpod_status_url("https://api.runpod.ai/v2/endpoint/runsync?wait=1000", "job-123")
        == "https://api.runpod.ai/v2/endpoint/status/job-123"
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


def test_runpod_mineru_result_is_normalized(monkeypatch):
    monkeypatch.setattr(ocr.settings, "ocr_runpod_contract", "mineru")
    result = _runpod_result(
        {
            "id": "mineru-job",
            "status": "COMPLETED",
            "output": {"results": [{"markdown": "# 견적서\n합계"}]},
        },
        file_name="quote.pdf",
    )

    assert result.payload["source_type"] == "runpod_mineru"
    assert result.payload["runpod_engine"] == "mineru"
    assert result.payload["pages"][0]["page_number"] == 1
    assert "합계" in result.markdown


def test_runpod_mineru_single_markdown_result_is_normalized(monkeypatch):
    monkeypatch.setattr(ocr.settings, "ocr_runpod_contract", "mineru")
    result = _runpod_result(
        {
            "status": "COMPLETED",
            "output": {"markdown": "Dummy PDF file"},
        },
        file_name="dummy.pdf",
    )

    assert result.payload["pages"][0]["page_number"] == 1
    assert result.plain_text == "Dummy PDF file"


def test_pdf_inspector_model_directory_uses_configured_path(monkeypatch):
    monkeypatch.setattr(ocr.settings, "pdf_inspector_model_directory", "~/salesluv-models")

    assert ocr._pdf_inspector_model_directory().endswith("/salesluv-models")


def test_pdf_inspector_model_directory_defaults_to_temp(monkeypatch):
    monkeypatch.setattr(ocr.settings, "pdf_inspector_model_directory", "")
    monkeypatch.setattr(ocr.tempfile, "gettempdir", lambda: "/tmp")

    assert ocr._pdf_inspector_model_directory().endswith("salesluv-pdf-inspector-models")


def test_pdf_inspector_model_directory_finds_nested_downloaded_artifacts(tmp_path, monkeypatch):
    nested = tmp_path / "pp-ocrv6-small" / "oar-ocr-v0.7.0"
    nested.mkdir(parents=True)
    (nested / "pp-ocrv6_small_det.onnx").write_bytes(b"model")
    monkeypatch.setattr(ocr.settings, "pdf_inspector_model_directory", str(tmp_path))

    assert ocr._pdf_inspector_model_directory() == str(nested)


def test_pdf_inspector_model_availability_controls_offline_mode(tmp_path):
    assert ocr._pdf_inspector_model_available(str(tmp_path)) is False
    (tmp_path / "pp-ocrv6_small_det.onnx").write_bytes(b"model")
    assert ocr._pdf_inspector_model_available(str(tmp_path)) is True


def test_pdf_inspector_model_cache_sets_library_environment(monkeypatch):
    monkeypatch.delenv("PDF_INSPECTOR_MODEL_CACHE", raising=False)
    monkeypatch.setattr(ocr.settings, "pdf_inspector_model_directory", "/tmp/salesluv-models")

    ocr._configure_pdf_inspector_model_cache()

    assert ocr.os.environ["PDF_INSPECTOR_MODEL_CACHE"] == "/tmp/salesluv-models"


def test_pdf_inspector_uses_default_download_mode_without_model(monkeypatch):
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
            {},
        )
    ]


def test_paddlex_cache_sets_library_environment(monkeypatch):
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    monkeypatch.delenv("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", raising=False)
    monkeypatch.setattr(ocr.settings, "paddlex_cache_home", "/tmp/salesluv-paddlex")

    ocr._configure_paddlex_cache()

    assert ocr.os.environ["PADDLE_PDX_CACHE_HOME"] == "/tmp/salesluv-paddlex"
    assert ocr.os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] == "True"


def test_business_card_ocr_lines_are_deduplicated_by_highest_confidence():
    result = ocr._merge_ocr_lines(
        [
            [
                {"content": "홍길동", "confidence": 0.81},
                {"content": "sales@example.com", "confidence": 0.90},
            ],
            [
                {"content": "홍길동", "confidence": 0.97},
                {"content": "영업팀", "confidence": 0.88},
            ],
        ]
    )

    assert result == [
        {"content": "홍길동", "confidence": 0.97},
        {"content": "sales@example.com", "confidence": 0.90},
        {"content": "영업팀", "confidence": 0.88},
    ]


def test_business_card_variants_cap_large_input_side(monkeypatch):
    from io import BytesIO

    from PIL import Image

    image = Image.new("RGB", (4_032, 3_024), "white")
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    monkeypatch.setattr(ocr.settings, "business_card_max_side", 2_400)
    monkeypatch.setattr(ocr, "_rectify_card", lambda value: None)

    variants = ocr._business_card_variants(buffer.getvalue())

    assert variants
    assert all(max(item.shape[:2]) <= 2_400 for item in variants)


def test_business_card_uses_lightweight_paddle_engine(monkeypatch):
    calls = []

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    fake_module = type("Module", (), {"PaddleOCR": FakePaddleOCR})
    monkeypatch.setitem(__import__("sys").modules, "paddleocr", fake_module)
    ocr._paddle_business_card_engine.cache_clear()
    monkeypatch.setattr(ocr, "_configure_paddlex_cache", lambda: None)

    ocr._paddle_business_card_engine()

    assert calls == [
        {
            "lang": ocr.settings.ocr_local_language,
            "text_detection_model_name": "PP-OCRv5_mobile_det",
            "text_recognition_model_name": "korean_PP-OCRv5_mobile_rec",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        }
    ]
    ocr._paddle_business_card_engine.cache_clear()


def test_paddle_lines_reads_paddlex_nested_json_result():
    results = [
        {"json": ('{"res":{"rec_texts":["오현미","010-1234-5678"],"rec_scores":[0.98,0.91]}}')}
    ]

    assert ocr._paddle_lines(results) == [
        {"content": "오현미", "confidence": 0.98},
        {"content": "010-1234-5678", "confidence": 0.91},
    ]


def test_paddle_lines_reads_paddlex_dict_json_result():
    results = [
        {
            "json": {
                "res": {
                    "rec_texts": ["제주한농부"],
                    "rec_scores": [0.97],
                }
            }
        }
    ]

    assert ocr._paddle_lines(results) == [{"content": "제주한농부", "confidence": 0.97}]


def test_paddle_engine_enables_card_orientation_and_unwarping(monkeypatch):
    calls = []

    class _PaddleOCR:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    module = type("Module", (), {"PaddleOCR": _PaddleOCR})
    monkeypatch.setitem(__import__("sys").modules, "paddleocr", module)
    ocr._paddle_engine.cache_clear()
    try:
        ocr._paddle_engine()
    finally:
        ocr._paddle_engine.cache_clear()

    assert calls[0]["use_doc_orientation_classify"] is True
    assert calls[0]["use_doc_unwarping"] is True
    assert calls[0]["use_textline_orientation"] is True


@pytest.mark.anyio
async def test_extract_document_passes_business_card_profile_to_local(monkeypatch):
    captured = {}

    def _local(**kwargs):
        captured.update(kwargs)
        return "local-result"

    monkeypatch.setattr(ocr.settings, "ocr_provider", "local")
    monkeypatch.setattr(ocr, "_local", _local)

    result = await ocr.extract_document(
        file_name="card.jpg",
        media_type="image/jpeg",
        content=b"image",
        profile="business_card",
    )

    assert result == "local-result"
    assert captured["profile"] == "business_card"


@pytest.mark.anyio
async def test_extract_document_passes_runpod_business_card_contract(monkeypatch):
    captured = {}

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "id": "job-123",
                "status": "COMPLETED",
                "output": {"pages": [{"page_number": 1, "markdown": "본문"}]},
            }

    class _Client:
        def __init__(self, **kwargs):
            captured["timeout"] = kwargs["timeout"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, endpoint, *, headers, json):
            captured.update({"endpoint": endpoint, "headers": headers, "json": json})
            return _Response()

    monkeypatch.setattr(ocr.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(ocr.settings, "ocr_provider", "runpod")
    monkeypatch.setattr(ocr.settings, "ocr_api_url", "https://runpod.test/v2/endpoint")
    monkeypatch.setattr(ocr.settings, "ocr_api_key", SecretStr("runpod-test-key"))
    monkeypatch.setattr(ocr.settings, "ocr_runpod_contract", "salesluv")
    monkeypatch.setattr(ocr.settings, "ocr_runpod_wait_seconds", 3)

    result = await ocr.extract_document(
        file_name="card.png",
        media_type="image/png",
        content=b"image",
        profile="business_card",
    )

    payload = captured["json"]["input"]
    assert result.payload["ocr_provider"] == "runpod"
    assert captured["endpoint"] == "https://runpod.test/v2/endpoint/runsync?wait=3000"
    assert payload["profile"] == "business_card"
    assert base64.b64decode(payload["content_base64"]) == b"image"
    assert captured["headers"]["Authorization"] == "Bearer runpod-test-key"


@pytest.mark.anyio
async def test_runpod_nonterminal_response_is_polled(monkeypatch):
    calls = []

    class _Response:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class _Client:
        def __init__(self, **_kwargs):
            self.closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            self.closed = True
            return None

        async def post(self, *_args, **_kwargs):
            return _Response({"id": "job-123", "status": "IN_PROGRESS"})

        async def get(self, endpoint, **_kwargs):
            assert self.closed is False
            calls.append(endpoint)
            return _Response(
                {
                    "id": "job-123",
                    "status": "COMPLETED",
                    "output": {"pages": [{"page_number": 1, "markdown": "본문"}]},
                }
            )

    monkeypatch.setattr(ocr.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(ocr.settings, "ocr_provider", "runpod")
    monkeypatch.setattr(ocr.settings, "ocr_api_url", "https://runpod.test/v2/endpoint")
    monkeypatch.setattr(ocr.settings, "ocr_api_key", SecretStr("runpod-test-key"))
    monkeypatch.setattr(ocr.settings, "ocr_runpod_contract", "salesluv")
    monkeypatch.setattr(ocr.settings, "ocr_runpod_wait_seconds", 3)
    monkeypatch.setattr(ocr.settings, "ocr_timeout_seconds", 1)

    result = await ocr.extract_document(
        file_name="card.png",
        media_type="image/png",
        content=b"image",
        profile="business_card",
    )

    assert result.payload["ocr_provider"] == "runpod"
    assert calls == ["https://runpod.test/v2/endpoint/status/job-123"]


@pytest.mark.anyio
async def test_extract_document_times_out_slow_local_ocr(monkeypatch):
    def _slow_local(**_kwargs):
        time.sleep(0.05)
        return "local-result"

    monkeypatch.setattr(ocr.settings, "ocr_provider", "local")
    monkeypatch.setattr(ocr.settings, "ocr_timeout_seconds", 0.001)
    monkeypatch.setattr(ocr, "_local", _slow_local)

    with pytest.raises(ocr.OcrError, match="local_ocr_timeout"):
        await ocr.extract_document(
            file_name="slow-card.jpg",
            media_type="image/jpeg",
            content=b"image",
            profile="business_card",
        )
