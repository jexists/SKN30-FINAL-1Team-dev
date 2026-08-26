"""스캔 문서 OCR 제공자 어댑터."""

from __future__ import annotations

import asyncio
import base64
import os
import tempfile
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from app.core.config import settings
from app.services.document_extraction import (
    ExtractedDocument,
    from_ocr_blocks,
    from_page_markdown,
)


class OcrError(Exception):
    """OCR 제공자 호출 실패."""


async def extract_document(
    *,
    file_name: str,
    media_type: str | None,
    content: bytes,
    source_url: str | None = None,
) -> ExtractedDocument:
    if not settings.ocr_configured:
        raise OcrError("ocr_provider_not_configured")
    if settings.ocr_provider == "local":
        return await asyncio.to_thread(
            _local,
            file_name=file_name,
            media_type=media_type,
            content=content,
        )
    if settings.ocr_provider == "runpod":
        return await _runpod(
            file_name=file_name,
            media_type=media_type,
            content=content,
            source_url=source_url,
        )
    if settings.ocr_provider != "azure":
        raise OcrError("ocr_provider_unsupported")
    return await _azure(file_name=file_name, media_type=media_type, content=content)


async def _runpod(
    *,
    file_name: str,
    media_type: str | None,
    content: bytes,
    source_url: str | None,
) -> ExtractedDocument:
    """Runpod Serverless OCR 워커를 동기 호출한다."""
    input_payload: dict[str, Any] = {
        "file_name": file_name,
        "media_type": media_type or "application/octet-stream",
        "language": settings.ocr_local_language,
    }
    if source_url:
        input_payload["source_url"] = source_url
    else:
        if len(content) > settings.ocr_runpod_inline_max_bytes:
            raise OcrError("runpod_source_url_required_for_large_file")
        input_payload["content_base64"] = base64.b64encode(content).decode("ascii")

    endpoint = _runpod_runsync_url(settings.ocr_api_url, settings.ocr_runpod_wait_seconds)
    try:
        async with httpx.AsyncClient(timeout=settings.ocr_timeout_seconds) as client:
            response = await client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {settings.ocr_api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json={"input": input_payload},
            )
    except httpx.HTTPError as error:
        raise OcrError(f"runpod_request_failed:{type(error).__name__}") from error
    if response.status_code >= 400:
        raise OcrError(f"runpod_provider_error:{response.status_code}")
    try:
        payload = response.json()
    except (ValueError, TypeError) as error:
        raise OcrError("runpod_response_not_json") from error
    if not isinstance(payload, dict):
        raise OcrError("runpod_response_invalid")
    status = str(payload.get("status", "")).upper()
    if status in {"FAILED", "CANCELED", "CANCELLED", "TIMED_OUT"}:
        raise OcrError("runpod_job_failed")
    return _runpod_result(payload, file_name=file_name)


def _runpod_runsync_url(api_url: str, wait_seconds: int) -> str:
    """ENDPOINT_ID URL 또는 이미 완성된 runsync URL 모두 허용한다."""
    url = api_url.rstrip("/")
    if not url.endswith("/runsync"):
        url = f"{url}/runsync"
    split = urlsplit(url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    query["wait"] = str(wait_seconds * 1000)
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


def _runpod_result(payload: dict[str, Any], *, file_name: str) -> ExtractedDocument:
    output = payload.get("output")
    if not isinstance(output, dict):
        raise OcrError("runpod_output_invalid")
    if output.get("error"):
        raise OcrError("runpod_worker_error")

    pages = output.get("pages")
    if not isinstance(pages, list) or not pages:
        raise OcrError("runpod_empty_result")
    common_extra = {
        "ocr_provider": "runpod",
        "source_file": file_name,
        "runpod_job_id": payload.get("id"),
        "runpod_status": payload.get("status"),
    }
    if all(isinstance(page, dict) and "markdown" in page for page in pages):
        return from_page_markdown(
            pages=pages,
            source_type="runpod_ocr",
            payload_extra=common_extra,
        )
    if all(isinstance(page, dict) and "lines" in page for page in pages):
        extracted = from_ocr_blocks(
            pages=pages,
            tables=output.get("tables") if isinstance(output.get("tables"), list) else [],
            source_type="runpod_ocr",
        )
        payload_copy = dict(extracted.payload)
        payload_copy.update(common_extra)
        return ExtractedDocument(
            plain_text=extracted.plain_text,
            markdown=extracted.markdown,
            payload=payload_copy,
        )
    raise OcrError("runpod_page_schema_invalid")


async def _azure(*, file_name: str, media_type: str | None, content: bytes) -> ExtractedDocument:
    headers = {
        "Ocp-Apim-Subscription-Key": settings.ocr_api_key.get_secret_value(),
        "Content-Type": media_type or "application/octet-stream",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.ocr_timeout_seconds) as client:
            response = await client.post(settings.ocr_api_url, headers=headers, content=content)
            if response.status_code == 202:
                operation_url = response.headers.get("Operation-Location")
                if not operation_url:
                    raise OcrError("ocr_operation_location_missing")
                result = await _poll_azure(client, operation_url)
            elif response.status_code < 400:
                result = response.json()
            else:
                raise OcrError(f"ocr_provider_error:{response.status_code}")
    except OcrError:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as error:
        raise OcrError(f"ocr_request_failed:{type(error).__name__}") from error
    return _azure_result(result, file_name=file_name)


async def _poll_azure(client: httpx.AsyncClient, operation_url: str) -> dict[str, Any]:
    for _ in range(120):
        response = await client.get(
            operation_url,
            headers={"Ocp-Apim-Subscription-Key": settings.ocr_api_key.get_secret_value()},
        )
        if response.status_code >= 400:
            raise OcrError(f"ocr_poll_error:{response.status_code}")
        payload = response.json()
        status = str(payload.get("status", "")).lower()
        if status == "succeeded":
            return payload
        if status in {"failed", "canceled"}:
            raise OcrError("ocr_processing_failed")
        await asyncio.sleep(0.5)
    raise OcrError("ocr_poll_timeout")


def _azure_result(payload: dict[str, Any], *, file_name: str) -> ExtractedDocument:
    result = payload.get("analyzeResult") or payload.get("result") or {}
    pages = []
    for index, page in enumerate(result.get("pages", []), start=1):
        pages.append(
            {
                "page_number": page.get("pageNumber", index),
                "lines": page.get("lines", []),
            }
        )
    if not pages and result.get("content"):
        pages = [{"page_number": 1, "lines": [{"content": result["content"]}]}]
    if not pages:
        raise OcrError("ocr_empty_result")
    extracted = from_ocr_blocks(
        pages=pages,
        tables=result.get("tables", []),
        source_type="azure_document_intelligence",
    )
    payload_copy = dict(extracted.payload)
    payload_copy["ocr_provider"] = "azure_document_intelligence"
    payload_copy["source_file"] = file_name
    return ExtractedDocument(
        plain_text=extracted.plain_text,
        markdown=extracted.markdown,
        payload=payload_copy,
    )


@lru_cache(maxsize=1)
def _paddle_engine():
    _configure_paddlex_cache()
    try:
        from paddleocr import PaddleOCR
    except ImportError as error:
        raise OcrError("local_ocr_dependency_missing:paddleocr") from error
    try:
        return PaddleOCR(
            lang=settings.ocr_local_language,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except TypeError:
        # PaddleOCR 2.x 호환용 옵션. 최신 버전의 옵션이 없는 설치를 지원한다.
        return PaddleOCR(lang=settings.ocr_local_language, use_angle_cls=True)


def _local(*, file_name: str, media_type: str | None, content: bytes) -> ExtractedDocument:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".pdf" or media_type == "application/pdf":
        return _local_pdf(content=content, file_name=file_name)
    return _local_image(content=content, file_name=file_name)


def _local_pdf(*, content: bytes, file_name: str) -> ExtractedDocument:
    """pdf-inspector의 선택적 로컬 OCR을 사용한다. 없으면 설치 오류를 명확히 반환한다."""
    # pdf-inspector가 import 시 PDFium을 초기화하므로, Mac·Windows에서
    # pypdfium2가 내려받은 네이티브 라이브러리 경로를 먼저 설정한다.
    _configure_pdfium()
    _configure_onnxruntime()
    _configure_pdf_inspector_model_cache()
    try:
        import pdf_inspector
    except ImportError as error:
        raise OcrError("local_pdf_ocr_dependency_missing:pdf-inspector") from error
    try:
        # pdf-inspector 1.17+는 모델 디렉터리와 offline 모드를 인자로 받는다.
        # 구버전 호환을 위해 해당 인자를 지원하지 않는 경우에만 기본 호출로
        # 재시도한다.
        try:
            result = pdf_inspector.process_pdf_with_ocr_bytes(
                content,
                model_directory=_pdf_inspector_model_directory(),
                offline=True,
            )
        except TypeError:
            result = pdf_inspector.process_pdf_with_ocr_bytes(content)
    except AttributeError as error:
        raise OcrError("local_pdf_ocr_api_unsupported") from error
    except Exception as error:
        raise OcrError(f"local_pdf_ocr_failed:{type(error).__name__}") from error

    page_results = _value(result, "pages")
    if not isinstance(page_results, list) or not page_results:
        raise OcrError("local_pdf_ocr_empty_result")
    pages: list[dict[str, Any]] = []
    for index, page in enumerate(page_results, start=1):
        provenance = _value(page, "provenance")
        pages.append(
            {
                "page_number": _value(page, "page_number") or index,
                "markdown": str(_value(page, "markdown") or ""),
                "source": _value(provenance, "source"),
                "ocr_confidence": _value(provenance, "ocr_confidence"),
                "needs_ocr": False,
            }
        )
    extracted = from_page_markdown(
        pages=pages,
        source_type="pdf_inspector_local_ocr",
        payload_extra={
            "pages_routed_to_ocr": _value(result, "pages_routed_to_ocr") or [],
            "pages_recommending_hosted": _value(result, "pages_recommending_hosted") or [],
        },
    )
    payload = dict(extracted.payload)
    payload.update(
        {
            "ocr_provider": "pdf_inspector_local_ocr",
            "source_file": file_name,
            "local_ocr": True,
        }
    )
    return ExtractedDocument(
        plain_text=extracted.plain_text,
        markdown=extracted.markdown,
        payload=payload,
    )


def _configure_pdfium() -> None:
    """pypdfium2가 설치된 Mac·Windows·Linux에서 pdf-inspector가 찾게 한다."""
    if os.environ.get("PDFIUM_LIB_PATH"):
        return
    try:
        import pypdfium2_raw
    except ImportError:
        return
    root = Path(pypdfium2_raw.__file__).parent
    candidates = [
        root / "libpdfium.dylib",
        root / "libpdfium.so",
        root / "libpdfium.dll",
        root / "pdfium.dll",
    ]
    for candidate in candidates:
        if candidate.is_file():
            os.environ["PDFIUM_LIB_PATH"] = str(candidate)
            return


def _configure_onnxruntime() -> None:
    """pdf-inspector가 찾을 수 있도록 설치된 ONNX Runtime 라이브러리를 지정한다."""
    if os.environ.get("ORT_DYLIB_PATH"):
        return
    try:
        import onnxruntime
    except ImportError:
        return
    root = Path(onnxruntime.__file__).parent / "capi"
    candidates = (
        root / "libonnxruntime.dylib",
        root / "libonnxruntime.so",
        root / "onnxruntime.dll",
    )
    for candidate in candidates:
        if candidate.is_file():
            os.environ["ORT_DYLIB_PATH"] = str(candidate)
            return
    for pattern in ("libonnxruntime*.dylib", "libonnxruntime*.so*", "onnxruntime*.dll"):
        matches = sorted(root.glob(pattern))
        if matches:
            os.environ["ORT_DYLIB_PATH"] = str(matches[0])
            return


def _pdf_inspector_model_directory() -> str:
    """pdf-inspector OCR 모델 캐시를 쓸 수 있는 플랫폼 공통 경로로 계산한다."""
    configured = settings.pdf_inspector_model_directory.strip()
    base = (
        Path(os.path.expanduser(configured))
        if configured
        else Path(tempfile.gettempdir()) / "salesluv-pdf-inspector-models"
    )
    # pdf-inspector가 자동 다운로드한 모델은 버전에 따라 중첩된 release
    # 디렉터리에 저장된다. 명시 호출에는 실제 artifact가 있는 폴더를 넘긴다.
    candidates = [
        base,
        base / "pp-ocrv6-small" / "oar-ocr-v0.7.0",
    ]
    for candidate in candidates:
        if (candidate / "pp-ocrv6_small_det.onnx").is_file():
            return str(candidate)
    return str(base)


def _configure_pdf_inspector_model_cache() -> None:
    """pdf-inspector의 자동 다운로드 캐시를 앱 설정 또는 OS 임시 폴더로 지정한다."""
    os.environ.setdefault("PDF_INSPECTOR_MODEL_CACHE", _pdf_inspector_model_directory())


def _paddlex_cache_directory() -> str:
    """PaddleX 공식 모델 캐시를 쓸 수 있는 플랫폼 공통 경로로 계산한다."""
    configured = settings.paddlex_cache_home.strip()
    if configured:
        return os.path.expanduser(configured)
    return os.path.join(tempfile.gettempdir(), "salesluv-paddlex-cache")


def _configure_paddlex_cache() -> None:
    """PaddleX 모델 다운로드·잠금 파일이 쓸 수 있는 경로를 지정한다."""
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", _paddlex_cache_directory())
    # 모델이 이미 캐시에 있으면 오프라인 환경에서도 호스트 확인 때문에
    # 초기화가 실패하지 않도록 한다. 캐시가 없을 때의 다운로드 실패는
    # PaddleX가 원래 오류로 반환한다.
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


def _local_image(*, content: bytes, file_name: str) -> ExtractedDocument:
    try:
        import numpy as np
        from PIL import Image
    except ImportError as error:
        raise OcrError("local_ocr_dependency_missing:pillow-numpy") from error
    try:
        image = np.asarray(Image.open(BytesIO(content)).convert("RGB"))
        engine = _paddle_engine()
        try:
            results = engine.predict(input=image)
        except AttributeError:
            results = engine.ocr(image, cls=True)
    except OcrError:
        raise
    except Exception as error:
        raise OcrError(f"local_ocr_failed:{type(error).__name__}") from error

    lines = _paddle_lines(results)
    if not lines:
        raise OcrError("local_ocr_empty_result")
    extracted = from_ocr_blocks(
        pages=[{"page_number": 1, "lines": lines}],
        source_type="paddleocr_local",
    )
    payload = dict(extracted.payload)
    payload.update(
        {
            "ocr_provider": "paddleocr_local",
            "source_file": file_name,
            "local_ocr": True,
        }
    )
    return ExtractedDocument(
        plain_text=extracted.plain_text,
        markdown=extracted.markdown,
        payload=payload,
    )


def _value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    candidate = getattr(value, key, None)
    if callable(candidate):
        candidate = candidate()
    return candidate


def _paddle_lines(results: Any) -> list[dict[str, Any]]:
    """PaddleOCR 2.x·3.x 결과를 공통 line 구조로 변환한다."""
    lines: list[dict[str, Any]] = []
    for result in results or []:
        data = _value(result, "res") or result
        json_data = _value(result, "json")
        if isinstance(json_data, str):
            import json

            try:
                data = json.loads(json_data)
            except ValueError:
                pass
        texts = _value(data, "rec_texts") or _value(data, "texts")
        scores = _value(data, "rec_scores") or _value(data, "scores")
        if isinstance(texts, list):
            for index, text in enumerate(texts):
                value = str(text).strip()
                if value:
                    lines.append(
                        {
                            "content": value,
                            "confidence": _at(scores, index),
                        }
                    )
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    pair = item[1]
                    if isinstance(pair, (list, tuple)) and pair:
                        value = str(pair[0]).strip()
                        if value:
                            lines.append(
                                {
                                    "content": value,
                                    "confidence": pair[1] if len(pair) > 1 else None,
                                }
                            )
    return lines


def _at(values: Any, index: int) -> Any:
    if isinstance(values, (list, tuple)) and index < len(values):
        return values[index]
    return None
