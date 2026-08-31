"""개인정보 없는 합성 입력으로 Runpod OCR 연결을 점검한다."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from app.services import ocr


def _synthetic_image() -> Image.Image:
    image = Image.new("RGB", (1_200, 500), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((60, 80), "SALESLUV OCR TEST", fill="black", font=font)
    draw.text((60, 180), "Synthetic Business Card", fill="black", font=font)
    draw.text((60, 300), "010-0000-0000", fill="black", font=font)
    return image


def _synthetic_card() -> bytes:
    buffer = BytesIO()
    _synthetic_image().save(buffer, format="PNG")
    return buffer.getvalue()


def _synthetic_pdf() -> bytes:
    buffer = BytesIO()
    _synthetic_image().save(buffer, format="PDF", resolution=150.0)
    return buffer.getvalue()


def _normalized(value: str) -> str:
    """OCR 공백·구두점 차이를 무시하고 합성 테스트 문자열을 비교한다."""
    return "".join(character.lower() for character in value if character.isalnum())


async def _run_case(case: str) -> dict[str, object]:
    if case == "business_card":
        file_name, media_type, profile, content = (
            "synthetic-business-card.png",
            "image/png",
            "business_card",
            _synthetic_card(),
        )
        expected_fragments = ("SALESLUV OCR TEST", "Synthetic Business Card")
    else:
        file_name, media_type, profile, content = (
            "synthetic-document.pdf",
            "application/pdf",
            "document",
            _synthetic_pdf(),
        )
        expected_fragments = ("SALESLUV OCR TEST", "Synthetic Business Card")

    started = time.perf_counter()
    try:
        result = await ocr.extract_document(
            file_name=file_name,
            media_type=media_type,
            content=content,
            profile=profile,
        )
    except Exception as error:
        return {
            "case": case,
            "status": "failed",
            "error_type": type(error).__name__,
            "error_code": str(error),
        }

    pages = result.payload.get("pages", [])
    normalized_text = _normalized(result.plain_text)
    expected_text_present = all(
        _normalized(fragment) in normalized_text for fragment in expected_fragments
    )
    return {
        "case": case,
        "status": (
            "passed" if result.plain_text.strip() and pages and expected_text_present else "failed"
        ),
        "provider": result.payload.get("ocr_provider"),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "page_count": len(pages),
        "page_numbers_sequential": [page.get("page_number") for page in pages]
        == list(range(1, len(pages) + 1)),
        "markdown_present": bool(result.markdown.strip()),
        "expected_text_present": expected_text_present,
    }


async def _main(cases: list[str]) -> int:
    results = [await _run_case(case) for case in cases]
    print(results)
    return 0 if all(item["status"] == "passed" for item in results) else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        choices=("business_card", "document", "all"),
        default="all",
        help="개인정보 없는 합성 명함 또는 PDF 테스트 유형",
    )
    args = parser.parse_args()
    cases = ["business_card", "document"] if args.case == "all" else [args.case]
    raise SystemExit(asyncio.run(_main(cases)))


if __name__ == "__main__":
    main()
