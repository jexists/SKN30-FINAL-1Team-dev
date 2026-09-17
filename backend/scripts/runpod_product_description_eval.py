"""Evaluate RunPod OCR on product-description PDF identifiers.

This produces only aggregate results.  The gold label is the product
identifier derived from each supplied PDF filename, so the score answers one
limited question: did OCR text contain the expected product identifier?
It does not measure full-document transcription, specification extraction,
or CER/WER.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent))

from runpod_ocr_dataset_eval import _clean, _gold_rows, _normalize

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import ocr

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data/sample/상품설명서_50개"
GOLD = ROOT / "output/evals/ocr-product-description/상품설명서_50개_제품식별자_정답지.xlsx"
OUT = ROOT / "output/evals/ocr-product-description/runpod_product_description_summary.json"


def _page_count(path: Path) -> int | None:
    try:
        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


async def _run_one(path: Path, expected_identifier: str) -> dict[str, object]:
    """Run one document, retrying one transient RunPod job failure."""
    started = time.perf_counter()
    last_error = "unknown"
    for attempt in range(1, 3):
        try:
            result = await ocr._runpod(
                file_name=path.name,
                media_type="application/pdf",
                content=path.read_bytes(),
                source_url=None,
                profile="document",
            )
            expected = _normalize(expected_identifier)
            return {
                "status": "success",
                "matched": bool(expected and expected in _normalize(result.plain_text)),
                "page_count": _page_count(path),
                "attempts": attempt,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
        except Exception as error:
            last_error = str(error)
            if attempt == 1:
                print(f"상품설명서: transient failure, retrying once ({path.name})", flush=True)
    return {
        "status": "error",
        "error_code": last_error,
        "attempts": 2,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


async def main() -> int:
    rows = _gold_rows(GOLD, sheet_index=1)
    jobs: list[tuple[Path, str]] = []
    for row in rows:
        filename = _clean(row.get("파일명"))
        expected = _clean(row.get("제품 식별자 정답"))
        path = DATASET / filename
        if path.is_file() and expected:
            jobs.append((path, expected))

    results: list[dict[str, object]] = []
    for index, (path, expected) in enumerate(jobs, start=1):
        results.append(await _run_one(path, expected))
        if index % 5 == 0 or index == len(jobs):
            print(f"상품설명서: {index}/{len(jobs)} completed", flush=True)

    success = [result for result in results if result["status"] == "success"]
    errors: dict[str, int] = {}
    for result in results:
        if result["status"] == "error":
            code = str(result.get("error_code", "unknown"))
            errors[code] = errors.get(code, 0) + 1
    matched = sum(int(bool(result["matched"])) for result in success)
    labeled = len(success)
    pages = sum(int(result["page_count"] or 0) for result in success)
    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "method": {
            "provider": "same configured RunPod Serverless OCR worker via backend OCR adapter",
            "input": "original product-description PDFs submitted through the RunPod PDF OCR route",
            "gold_label": "product identifier derived from each supplied PDF filename",
            "field_metric": "normalized expected-product-identifier containment in OCR plain text",
            "retry_policy": "one immediate retry only when a RunPod OCR request fails",
            "scope": (
                "product identifier extraction only; not full-document OCR accuracy, "
                "specification-value accuracy, CER/WER, or field-location "
                "accuracy"
            ),
            "raw_text_persisted": False,
        },
        "dataset": {
            "input_count": len(jobs),
            "success_count": len(success),
            "error_count": len(jobs) - len(success),
            "processed_pdf_pages": pages,
            "retried_document_count": sum(int(result.get("attempts", 1)) > 1 for result in results),
            "product_identifier": {
                "matched": matched,
                "labeled": labeled,
                "success_only_accuracy": round(matched / labeled, 4) if labeled else None,
                "end_to_end_accuracy": round(matched / len(jobs), 4) if jobs else None,
            },
            "errors_by_code": errors,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    score = f"{matched / labeled * 100:.1f}%" if labeled else "not_scored"
    print(f"상품설명서 제품 식별자: {matched}/{labeled} = {score}", flush=True)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
