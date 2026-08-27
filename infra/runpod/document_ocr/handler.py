"""Runpod Serverless 자료요약용 OCR 워커.

입력은 source_url 또는 content_base64 중 하나이며, 출력은 백엔드 OCR 어댑터가
정규화할 수 있는 페이지별 markdown 계약을 따른다.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
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
        profile = str(input_data.get("profile") or "document")
        if media_type == "application/pdf" or file_name.lower().endswith(".pdf"):
            pages = _pdf_pages(content)
        else:
            pages = [_image_page(content, language=language, profile=profile)]
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
            use_doc_orientation_classify=True,
            use_doc_unwarping=True,
            use_textline_orientation=True,
        )
    except TypeError:
        return PaddleOCR(lang=language, use_angle_cls=True)


@lru_cache(maxsize=4)
def _paddle_business_card_engine(language: str):
    """명함용 경량 엔진. 전처리한 사진에 문서용 보정을 반복하지 않는다."""
    from paddleocr import PaddleOCR

    try:
        return PaddleOCR(
            lang=language,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except TypeError:
        return PaddleOCR(lang=language, use_angle_cls=False)


def _image_page(content: bytes, *, language: str, profile: str = "document") -> dict:
    import numpy as np
    from PIL import Image

    images = _business_card_variants(content) if profile == "business_card" else [
        np.asarray(Image.open(BytesIO(content)).convert("RGB"))
    ]
    engine = (
        _paddle_business_card_engine(language)
        if profile == "business_card"
        else _paddle_engine(language)
    )
    line_groups = []
    for image in images:
        try:
            results = engine.predict(input=image)
        except AttributeError:
            results = engine.ocr(image, cls=True)
        line_groups.append(_lines(results))
    lines = _merge_lines(line_groups) if profile == "business_card" else line_groups[0]
    markdown = "\n".join(line["content"] for line in lines if line["content"]).strip()
    return {
        "page_number": 1,
        "markdown": markdown,
        "source": "paddleocr",
        "ocr_profile": profile,
        "ocr_variant_count": len(images),
        "ocr_confidence": min(
            (line["confidence"] for line in lines if line["confidence"] is not None),
            default=None,
        ),
    }


def _business_card_variants(content: bytes) -> list:
    import numpy as np
    from PIL import Image, ImageEnhance, ImageOps

    image = ImageOps.exif_transpose(Image.open(BytesIO(content))).convert("RGB")
    base = np.asarray(image)
    rectified = _rectify_card(base)
    if rectified is not None:
        base = rectified

    try:
        max_side = max(640, min(int(os.getenv("BUSINESS_CARD_MAX_SIDE", "2400")), 6000))
    except ValueError:
        max_side = 2400
    height, width = base.shape[:2]
    longest_side = max(height, width)
    if longest_side > max_side:
        scale = max_side / longest_side
        resized = Image.fromarray(base).resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.Resampling.LANCZOS,
        )
        base = np.asarray(resized)

    gray = ImageOps.grayscale(Image.fromarray(base))
    enhanced = ImageEnhance.Contrast(ImageOps.autocontrast(gray)).enhance(1.35)
    variants = [base, np.asarray(enhanced.convert("RGB"))]
    try:
        import cv2

        threshold = cv2.adaptiveThreshold(
            np.asarray(enhanced),
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


def _rectify_card(image):
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 30, 120)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:10]:
        if cv2.contourArea(contour) < height * width * 0.20:
            continue
        polygon = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
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


def _order_quad(points):
    import numpy as np

    ordered = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).ravel()
    ordered[0] = points[np.argmin(sums)]
    ordered[2] = points[np.argmax(sums)]
    ordered[1] = points[np.argmin(differences)]
    ordered[3] = points[np.argmax(differences)]
    return ordered


def _merge_lines(line_groups: list[list[dict]]) -> list[dict]:
    merged: list[dict] = []
    positions: dict[str, int] = {}
    for lines in line_groups:
        for line in lines:
            content = str(line.get("content", "")).strip()
            if not content:
                continue
            key = " ".join(content.casefold().split())
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


def _as_sequence(value):
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


def _value(value, key):
    if isinstance(value, dict):
        return value.get(key)
    candidate = getattr(value, key, None)
    if callable(candidate):
        candidate = candidate()
    return candidate


def _at(values, index):
    values = _as_sequence(values)
    if values is not None and index < len(values):
        return values[index]
    return None


def _safe_error(error: Exception) -> str:
    value = str(error)
    return value if value and len(value) <= 120 else type(error).__name__


if __name__ == "__main__":
    import runpod

    runpod.serverless.start({"handler": handler})
