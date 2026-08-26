"""Windows CI에서 로컬 OCR 런타임과 실제 이미지 추론을 확인한다."""

from __future__ import annotations

import argparse
import asyncio
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# `python scripts/windows_ocr_smoke.py`처럼 백엔드 디렉터리에서 직접 실행해도
# `app` 패키지를 찾도록 프로젝트 루트를 명시한다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ocr import extract_document


def _synthetic_image() -> bytes:
    """외부 개인정보 없이 OCR에 넣을 큰 영문 테스트 이미지를 만든다."""
    small = Image.new("RGB", (240, 60), "white")
    draw = ImageDraw.Draw(small)
    draw.text((8, 15), "SALESLUV OCR 123", fill="black", font=ImageFont.load_default())
    image = small.resize((1920, 480), Image.Resampling.NEAREST)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--file",
        type=Path,
        help="실제 이미지 경로. 생략하면 개인정보 없는 합성 이미지를 사용한다.",
    )
    args = parser.parse_args()
    if args.file is None:
        file_name = "windows-ocr-smoke.png"
        content = _synthetic_image()
        media_type = "image/png"
    else:
        file_name = args.file.name
        content = args.file.read_bytes()
        media_type = "image/jpeg" if args.file.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    result = await extract_document(
        file_name=file_name,
        media_type=media_type,
        content=content,
    )
    if result.payload.get("ocr_provider") != "paddleocr_local":
        raise RuntimeError("local_ocr_provider_not_used")
    if not result.plain_text.strip():
        raise RuntimeError("local_ocr_returned_empty_text")
    if result.payload.get("pages", [{}])[0].get("page_number") != 1:
        raise RuntimeError("local_ocr_page_number_missing")
    print("windows_ocr_smoke=passed")


if __name__ == "__main__":
    asyncio.run(main())
