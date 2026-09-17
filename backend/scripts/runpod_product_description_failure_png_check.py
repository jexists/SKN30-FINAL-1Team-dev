"""Check whether the failed product-description PDF can be recovered by image OCR.

Stores only pass/fail aggregates, never OCR text.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import ocr

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/sample/상품설명서_50개/urf-v.pdf"
OUTPUT = (
    ROOT / "output/evals/ocr-product-description/runpod_product_description_failure_png_check.json"
)
EXPECTED = "urf-v"


def normalize(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


async def main() -> None:
    result = await ocr.extract_document(
        file_name=SOURCE.name,
        media_type="application/pdf",
        content=SOURCE.read_bytes(),
        source_url=None,
        profile="document",
    )
    fallback = result.payload.get("ocr_fallback", {})
    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "input": "urf-v.pdf only, processed through the production OCR entry point",
        "provider": "same configured RunPod Serverless OCR worker via backend OCR adapter",
        "expected_identifier": EXPECTED,
        "source_type": result.payload.get("source_type"),
        "fallback_reason": fallback.get("reason"),
        "rendered_page_count": fallback.get("rendered_page_count", 0),
        "matched": normalize(EXPECTED) in normalize(result.plain_text),
        "raw_text_persisted": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
