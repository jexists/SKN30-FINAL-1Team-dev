"""Runpod Serverless 자료요약용 OCR 워커.

입력은 source_url 또는 content_base64 중 하나이며, 출력은 백엔드 OCR 어댑터가
정규화할 수 있는 페이지별 markdown 계약을 따른다.
"""

from __future__ import annotations

import base64
import json
import mimetypes
from functools import lru_cache
from io import BytesIO
from urllib.request import Request, urlopen


def handler(job: dict) -> dict:
    try:
        input_data = job.get("input") if isinstance(job, dict) else None
        if not isinstance(input_data, dict):
            raise ValueError("input_required")
        content = _read_content(input_data)
        file_name = str(input_data.get("file_name") or "document")
        media_type = str(
            input_data.get("media_type")
            or mimetypes.guess_type(file_name)[0]
            or "application/octet-stream"
        )
        language = str(input_data.get("language") or "korean")
        if media_type == "application/pdf" or file_name.lower().endswith(".pdf"):
            pages = _pdf_pages(content)
        else:
            pages = [_image_page(content, language=language)]
        if not pages or not any(str(page.get("markdown", "")).strip() for page in pages):
            raise ValueError("ocr_empty_result")
        return {"pages": pages}
    except Exception as error:
        # 백엔드는 output.error를 안전한 상태 코드로 바꾼다. 원본·키·URL은 반환하지 않는다.
        return {"error": _safe_error(error)}


def _read_content(input_data: dict) -> bytes:
    source_url = input_data.get("source_url")
    if isinstance(source_url, str) and source_url:
        request = Request(source_url, headers={"User-Agent": "salesluv-document-ocr/1"})
        with urlopen(request, timeout=120) as response:  # noqa: S310 - URL은 백엔드가 발급한다.
            content = response.read()
    else:
        encoded = input_data.get("content_base64")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("source_url_or_content_base64_required")
        content = base64.b64decode(encoded, validate=True)
    if not content:
        raise ValueError("empty_input")
    return content


def _pdf_pages(content: bytes) -> list[dict]:
    import pdf_inspector

    result = pdf_inspector.process_pdf_with_ocr_bytes(content)
    pages: list[dict] = []
    for index, page in enumerate(_value(result, "pages") or [], start=1):
        provenance = _value(page, "provenance")
        pages.append(
            {
                "page_number": _value(page, "page_number") or index,
                "markdown": str(_value(page, "markdown") or ""),
                "source": _value(provenance, "source") or "pdf_inspector",
                "ocr_confidence": _value(provenance, "ocr_confidence"),
            }
        )
    return pages


@lru_cache(maxsize=4)
def _paddle_engine(language: str):
    from paddleocr import PaddleOCR

    try:
        return PaddleOCR(
            lang=language,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except TypeError:
        return PaddleOCR(lang=language, use_angle_cls=True)


def _image_page(content: bytes, *, language: str) -> dict:
    import numpy as np
    from PIL import Image

    image = np.asarray(Image.open(BytesIO(content)).convert("RGB"))
    engine = _paddle_engine(language)
    try:
        results = engine.predict(input=image)
    except AttributeError:
        results = engine.ocr(image, cls=True)
    lines = _lines(results)
    markdown = "\n".join(line["content"] for line in lines if line["content"]).strip()
    return {
        "page_number": 1,
        "markdown": markdown,
        "source": "paddleocr",
        "ocr_confidence": min(
            (line["confidence"] for line in lines if line["confidence"] is not None),
            default=None,
        ),
    }


def _lines(results) -> list[dict]:
    lines: list[dict] = []
    for result in results or []:
        data = _value(result, "res") or result
        json_data = _value(result, "json")
        if isinstance(json_data, str):
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
                    lines.append({"content": value, "confidence": _at(scores, index)})
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


def _value(value, key):
    if isinstance(value, dict):
        return value.get(key)
    candidate = getattr(value, key, None)
    if callable(candidate):
        candidate = candidate()
    return candidate


def _at(values, index):
    if isinstance(values, (list, tuple)) and index < len(values):
        return values[index]
    return None


def _safe_error(error: Exception) -> str:
    value = str(error)
    return value if value and len(value) <= 120 else type(error).__name__


if __name__ == "__main__":
    import runpod

    runpod.serverless.start({"handler": handler})
