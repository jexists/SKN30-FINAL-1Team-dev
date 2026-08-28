"""스캔 문서 OCR 제공자 어댑터."""

from __future__ import annotations

import asyncio
import base64
import os
import re
import tempfile
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

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
    profile: str = "document",
) -> ExtractedDocument:
    if not settings.ocr_configured:
        raise OcrError("ocr_provider_not_configured")
    if settings.ocr_provider == "local":
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    _local,
                    file_name=file_name,
                    media_type=media_type,
                    content=content,
                    profile=profile,
                ),
                timeout=settings.ocr_timeout_seconds,
            )
        except TimeoutError as error:
            raise OcrError("local_ocr_timeout") from error
    if settings.ocr_provider == "runpod":
        return await _runpod(
            file_name=file_name,
            media_type=media_type,
            content=content,
            source_url=source_url,
            profile=profile,
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
    profile: str,
) -> ExtractedDocument:
    """Runpod Serverless OCR 워커를 동기 호출한다."""
    input_payload: dict[str, Any] = {
        "file_name": file_name,
        "media_type": media_type or "application/octet-stream",
        "language": settings.ocr_local_language,
        "profile": profile,
    }
    if source_url:
        source_key = "file_url" if settings.ocr_runpod_contract == "mineru" else "source_url"
        input_payload[source_key] = source_url
    else:
        if len(content) > settings.ocr_runpod_inline_max_bytes:
            raise OcrError("runpod_source_url_required_for_large_file")
        content_key = (
            "file_b64" if settings.ocr_runpod_contract == "mineru" else "content_base64"
        )
        input_payload[content_key] = base64.b64encode(content).decode("ascii")

    if settings.ocr_runpod_contract == "mineru":
        input_payload.update(
            {"transport": "inline", "formats": ["markdown", "content_list", "middle"]}
        )

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
            if status in {"IN_QUEUE", "IN_PROGRESS"}:
                job_id = payload.get("id")
                if not isinstance(job_id, str) or not job_id:
                    raise OcrError("runpod_job_id_missing")
                payload = await _poll_runpod(client, settings.ocr_api_url, job_id)
    except httpx.HTTPError as error:
        raise OcrError(f"runpod_request_failed:{type(error).__name__}") from error
    return _runpod_result(payload, file_name=file_name)


async def _poll_runpod(client: httpx.AsyncClient, api_url: str, job_id: str) -> dict[str, Any]:
    """runsync가 먼저 반환한 비동기 job을 완료까지 확인한다."""
    deadline = asyncio.get_running_loop().time() + settings.ocr_timeout_seconds
    status_url = _runpod_status_url(api_url, job_id)
    headers = {
        "Authorization": f"Bearer {settings.ocr_api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }
    while asyncio.get_running_loop().time() < deadline:
        try:
            response = await client.get(status_url, headers=headers)
        except httpx.HTTPError as error:
            raise OcrError(f"runpod_poll_failed:{type(error).__name__}") from error
        if response.status_code >= 400:
            raise OcrError(f"runpod_poll_error:{response.status_code}")
        try:
            payload = response.json()
        except (ValueError, TypeError) as error:
            raise OcrError("runpod_response_not_json") from error
        if not isinstance(payload, dict):
            raise OcrError("runpod_response_invalid")
        status = str(payload.get("status", "")).upper()
        if status in {"COMPLETED", "FAILED", "CANCELED", "CANCELLED", "TIMED_OUT"}:
            if status != "COMPLETED":
                raise OcrError("runpod_job_failed")
            return payload
        await asyncio.sleep(0.5)
    raise OcrError("runpod_poll_timeout")


def _runpod_runsync_url(api_url: str, wait_seconds: int) -> str:
    """ENDPOINT_ID URL 또는 이미 완성된 runsync URL 모두 허용한다."""
    url = api_url.rstrip("/")
    if not url.endswith("/runsync"):
        url = f"{url}/runsync"
    split = urlsplit(url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    query["wait"] = str(wait_seconds * 1000)
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


def _runpod_status_url(api_url: str, job_id: str) -> str:
    """ENDPOINT_ID URL 또는 runsync URL에서 상태 조회 URL을 만든다."""
    split = urlsplit(api_url.rstrip("/"))
    path = split.path
    if path.endswith("/runsync"):
        path = path[: -len("/runsync")]
    return urlunsplit(
        (split.scheme, split.netloc, f"{path}/status/{quote(job_id, safe='')}", "", "")
    )


def _runpod_result(payload: dict[str, Any], *, file_name: str) -> ExtractedDocument:
    output = payload.get("output")
    if not isinstance(output, dict):
        raise OcrError("runpod_output_invalid")
    if output.get("error"):
        raise OcrError("runpod_worker_error")

    common_extra = {
        "ocr_provider": "runpod",
        "source_file": file_name,
        "runpod_job_id": payload.get("id"),
        "runpod_status": payload.get("status"),
    }
    pages = output.get("pages")
    if isinstance(pages, list) and pages:
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
    if settings.ocr_runpod_contract == "mineru":
        return _mineru_result(output, common_extra=common_extra)
    raise OcrError("runpod_empty_result")


def _mineru_result(output: dict[str, Any], *, common_extra: dict[str, Any]) -> ExtractedDocument:
    """MinerU results[] 또는 단일 markdown 응답을 페이지 계약으로 정규화한다."""
    direct_markdown = output.get("markdown")
    if isinstance(direct_markdown, str) and direct_markdown.strip():
        return from_page_markdown(
            pages=[{"page_number": 1, "markdown": direct_markdown, "source": "mineru"}],
            source_type="runpod_mineru",
            payload_extra={**common_extra, "runpod_engine": "mineru"},
        )
    results = output.get("results")
    if not isinstance(results, list) or not results:
        raise OcrError("runpod_empty_result")
    pages: list[dict[str, Any]] = []
    for index, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            continue
        markdown = item.get("markdown")
        if isinstance(markdown, str) and markdown.strip():
            pages.append({"page_number": index, "markdown": markdown, "source": "mineru"})
    if not pages:
        raise OcrError("runpod_empty_result")
    return from_page_markdown(
        pages=pages,
        source_type="runpod_mineru",
        payload_extra={**common_extra, "runpod_engine": "mineru"},
    )


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
            use_doc_orientation_classify=True,
            use_doc_unwarping=True,
            use_textline_orientation=True,
        )
    except TypeError:
        # PaddleOCR 2.x 호환용 옵션. 최신 버전의 옵션이 없는 설치를 지원한다.
        return PaddleOCR(lang=settings.ocr_local_language, use_angle_cls=True)


@lru_cache(maxsize=1)
def _paddle_business_card_engine():
    """명함용 CPU 경량 엔진. 이미 보정한 사진에는 문서 전처리를 반복하지 않는다."""
    _configure_paddlex_cache()
    try:
        from paddleocr import PaddleOCR
    except ImportError as error:
        raise OcrError("local_ocr_dependency_missing:paddleocr") from error
    try:
        return PaddleOCR(
            lang=settings.ocr_local_language,
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except TypeError:
        # PaddleOCR 2.x 호환용: 명함 사진은 각도 보정 없이 이미 전처리한다.
        return PaddleOCR(lang=settings.ocr_local_language, use_angle_cls=False)


def _local(
    *, file_name: str, media_type: str | None, content: bytes, profile: str = "document"
) -> ExtractedDocument:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".pdf" or media_type == "application/pdf":
        return _local_pdf(content=content, file_name=file_name)
    return _local_image(content=content, file_name=file_name, profile=profile)


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
        model_directory = _pdf_inspector_model_directory()
        offline = _pdf_inspector_model_available(model_directory)
        try:
            if offline:
                result = pdf_inspector.process_pdf_with_ocr_bytes(
                    content,
                    model_directory=model_directory,
                    offline=True,
                )
            else:
                # 모델 디렉터리를 명시하면 pdf-inspector 일부 버전이
                # 자동 다운로드 대신 "incomplete directory"로 중단한다.
                result = pdf_inspector.process_pdf_with_ocr_bytes(content)
        except TypeError:
            result = pdf_inspector.process_pdf_with_ocr_bytes(content)
    except ValueError as error:
        if not locals().get("offline", False):
            raise OcrError("local_pdf_ocr_model_unavailable") from error
        raise OcrError("local_pdf_ocr_failed:ValueError") from error
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


def _pdf_inspector_model_available(model_directory: str) -> bool:
    """모델 파일이 있으면 오프라인 모드로, 없으면 최초 다운로드 모드로 실행한다."""
    return (Path(model_directory) / "pp-ocrv6_small_det.onnx").is_file()


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


def _local_image(
    *, content: bytes, file_name: str, profile: str = "document"
) -> ExtractedDocument:
    try:
        import numpy as np
        from PIL import Image
    except ImportError as error:
        raise OcrError("local_ocr_dependency_missing:pillow-numpy") from error
    try:
        images = (
            _business_card_variants(content)
            if profile == "business_card"
            else [np.asarray(Image.open(BytesIO(content)).convert("RGB"))]
        )
        engine = (
            _paddle_business_card_engine()
            if profile == "business_card"
            else _paddle_engine()
        )
        line_groups = []
        for image in images:
            try:
                results = engine.predict(input=image)
            except AttributeError:
                results = engine.ocr(image, cls=True)
            line_groups.append(_paddle_lines(results))
    except OcrError:
        raise
    except Exception as error:
        raise OcrError(f"local_ocr_failed:{type(error).__name__}") from error

    lines = _merge_ocr_lines(line_groups) if profile == "business_card" else line_groups[0]
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
            "ocr_profile": profile,
            "ocr_variant_count": len(images),
        }
    )
    return ExtractedDocument(
        plain_text=extracted.plain_text,
        markdown=extracted.markdown,
        payload=payload,
    )


def _business_card_variants(content: bytes) -> list[Any]:
    """명함 사진을 보정한 OCR 입력을 만든다.

    OpenCV가 설치된 환경에서는 사각형 검출·원근 보정을 먼저 시도하고,
    설치되지 않은 환경에서도 Pillow 기반 대비 보정은 계속 제공한다.
    """
    import numpy as np
    from PIL import Image, ImageEnhance, ImageOps

    image = ImageOps.exif_transpose(Image.open(BytesIO(content))).convert("RGB")
    base = np.asarray(image)

    # 원본 사진을 먼저 줄인 뒤 외곽선·원근 보정을 한다. 4K 휴대폰 사진을
    # 원본 크기 그대로 OpenCV에 넣으면 카드 검출 단계부터 CPU 시간이 크게 늘어난다.
    base = _resize_longest_side(base, settings.business_card_max_side)
    rectified = _rectify_card(base)
    if rectified is not None:
        base = rectified
    base = _resize_longest_side(base, settings.business_card_max_side)

    gray = ImageOps.grayscale(Image.fromarray(base))
    enhanced = ImageEnhance.Contrast(ImageOps.autocontrast(gray)).enhance(1.35)
    variants = [base, np.asarray(enhanced.convert("RGB"))]

    try:
        import cv2

        gray_array = np.asarray(enhanced)
        threshold = cv2.adaptiveThreshold(
            gray_array,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
        variants.append(np.repeat(threshold[:, :, None], 3, axis=2))
    except ImportError:
        pass
    return variants


def _resize_longest_side(image: Any, max_side: int) -> Any:
    """이미지의 긴 변만 제한해 OCR 입력 크기를 안정적으로 유지한다."""
    import numpy as np
    from PIL import Image

    height, width = image.shape[:2]
    longest_side = max(height, width)
    if longest_side <= max_side:
        return image
    scale = max_side / longest_side
    resized = Image.fromarray(image).resize(
        (max(1, round(width * scale)), max(1, round(height * scale))),
        Image.Resampling.LANCZOS,
    )
    return np.asarray(resized)


def _rectify_card(image: Any) -> Any | None:
    """사진 속 명함 외곽선을 찾아 원근을 보정한다. 실패하면 원본을 유지한다."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 30, 120)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:10]:
        area = cv2.contourArea(contour)
        if area < height * width * 0.20:
            continue
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(polygon) != 4:
            continue
        points = _order_quad(polygon.reshape(4, 2))
        top_left, top_right, bottom_right, bottom_left = points
        target_width = max(
            int(np.linalg.norm(top_right - top_left)),
            int(np.linalg.norm(bottom_right - bottom_left)),
        )
        target_height = max(
            int(np.linalg.norm(bottom_left - top_left)),
            int(np.linalg.norm(bottom_right - top_right)),
        )
        if target_width < 100 or target_height < 60:
            continue
        destination = np.array(
            [
                [0, 0],
                [target_width - 1, 0],
                [target_width - 1, target_height - 1],
                [0, target_height - 1],
            ],
            dtype=np.float32,
        )
        transform = cv2.getPerspectiveTransform(points.astype(np.float32), destination)
        return cv2.warpPerspective(image, transform, (target_width, target_height))
    return None


def _order_quad(points: Any) -> Any:
    import numpy as np

    ordered = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).ravel()
    ordered[0] = points[np.argmin(sums)]
    ordered[2] = points[np.argmax(sums)]
    ordered[1] = points[np.argmin(differences)]
    ordered[3] = points[np.argmax(differences)]
    return ordered


def _merge_ocr_lines(line_groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """보정 variant 결과를 중복 제거하고 confidence가 높은 값을 남긴다."""
    merged: list[dict[str, Any]] = []
    positions: dict[str, int] = {}
    for lines in line_groups:
        for line in lines:
            content = str(line.get("content", "")).strip()
            if not content:
                continue
            key = re.sub(r"\s+", " ", content).casefold()
            candidate = {"content": content, "confidence": line.get("confidence")}
            if key not in positions:
                positions[key] = len(merged)
                merged.append(candidate)
                continue
            index = positions[key]
            current = merged[index].get("confidence")
            incoming = candidate.get("confidence")
            if isinstance(incoming, (int, float)) and (
                not isinstance(current, (int, float)) or incoming > current
            ):
                merged[index] = candidate
    return merged


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
        elif isinstance(json_data, dict):
            data = json_data
        # PaddleOCR 3.x의 Result.json()은 {"res": {...}} 형태를 반환할 수
        # 있다. 이 경우 rec_texts가 한 단계 안쪽에 있으므로 펼친다.
        nested = _value(data, "res")
        if nested is not None:
            data = nested
        texts = _value(data, "rec_texts") or _value(data, "texts")
        scores = _value(data, "rec_scores") or _value(data, "scores")
        text_values = _as_sequence(texts)
        if text_values is not None:
            for index, text in enumerate(text_values):
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


def _as_sequence(value: Any) -> list[Any] | tuple[Any, ...] | None:
    """numpy 배열 등 PaddleOCR 결과 컨테이너를 안전하게 순회한다."""
    if isinstance(value, (list, tuple)):
        return value
    if value is None or isinstance(value, (str, bytes, dict)):
        return None
    try:
        converted = value.tolist()
    except AttributeError:
        return None
    return converted if isinstance(converted, (list, tuple)) else None


def _at(values: Any, index: int) -> Any:
    values = _as_sequence(values)
    if values is not None and index < len(values):
        return values[index]
    return None
