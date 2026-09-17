"""Re-run the final OCR policy without retaining OCR text or source documents.

Policy under test:
* contracts: original RunPod PDF OCR, then rendered-PNG OCR when Korean text is missing;
  score the rendered-PNG result for every selected field.
* purchase orders: run both paths; use PDF OCR only for ``공급자 주소`` and rendered-PNG
  OCR for the other selected fields.

The result is an aggregate-only evaluation artifact. It is not a substitute for
structured field persistence in the product runtime.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from runpod_ocr_dataset_eval import (
    _clean,
    _dataset_specs,
    _expected_variants,
    _file_from_name,
    _gold_rows,
    _normalize,
)

from app.services import ocr


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/evals/ocr-final-policy/runpod_final_policy_summary.json"
TARGETS = {"계약서", "발주서"}
PDF_SOURCE_FIELDS = {"발주서": {"공급자 주소"}}


def _matches(text: str, expected: dict[str, str], fields: list[str]) -> dict[str, bool]:
    normalized = _normalize(text)
    return {
        field: any(variant in normalized for variant in _expected_variants(field, value))
        for field, value in expected.items()
        if field in fields and _clean(value)
    }


async def _rendered_text(
    path: Path,
    *,
    semaphore: asyncio.Semaphore,
    render_semaphore: asyncio.Semaphore,
) -> tuple[str, int]:
    async with render_semaphore:
        pages = await asyncio.to_thread(ocr.render_pdf_pages_png, path.read_bytes())
    text_pages: list[str] = []
    for page_number, png in enumerate(pages, start=1):
        async with semaphore:
            result = await ocr._runpod(
                file_name=f"{path.stem}-page-{page_number}.png",
                media_type="image/png",
                content=png,
                source_url=None,
                profile="document",
            )
        text_pages.append(result.plain_text)
    return "\n".join(text_pages), len(pages)


async def _run_one(
    item: dict[str, object],
    *,
    semaphore: asyncio.Semaphore,
    render_semaphore: asyncio.Semaphore,
) -> dict[str, object]:
    path: Path = item["path"]  # type: ignore[assignment]
    name = str(item["name"])
    started = time.perf_counter()
    try:
        async with semaphore:
            pdf_result = await ocr._runpod(
                file_name=path.name,
                media_type="application/pdf",
                content=path.read_bytes(),
                source_url=None,
                profile="document",
            )
        png_text, page_count = await _rendered_text(
            path, semaphore=semaphore, render_semaphore=render_semaphore
        )
        expected: dict[str, str] = item["expected"]  # type: ignore[assignment]
        fields: list[str] = item["fields"]  # type: ignore[assignment]
        pdf_matches = _matches(pdf_result.plain_text, expected, fields)
        png_matches = _matches(png_text, expected, fields)
        selected = {
            field: (pdf_matches[field] if field in PDF_SOURCE_FIELDS.get(name, set()) else png_matches[field])
            for field in png_matches
        }
        return {
            "status": "success",
            "page_count": page_count,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "selected_matches": selected,
            "pdf_matches": pdf_matches,
            "png_matches": png_matches,
        }
    except Exception as error:
        return {
            "status": "error",
            "error_code": str(error),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }


def _aggregate(items: list[dict[str, object]], results: list[dict[str, object]]) -> dict[str, object]:
    bucket: dict[str, object] = {
        "input_count": len(items),
        "success_count": 0,
        "error_count": 0,
        "processed_png_pages": 0,
        "field_matches": {},
        "errors_by_code": {},
    }
    for result in results:
        if result["status"] == "success":
            bucket["success_count"] = int(bucket["success_count"]) + 1
            bucket["processed_png_pages"] = int(bucket["processed_png_pages"]) + int(result["page_count"])
            for field, matched in result["selected_matches"].items():  # type: ignore[union-attr]
                stats = bucket["field_matches"].setdefault(field, {"matched": 0, "labeled": 0})  # type: ignore[union-attr]
                stats["matched"] += int(bool(matched))
                stats["labeled"] += 1
        else:
            bucket["error_count"] = int(bucket["error_count"]) + 1
            code = str(result["error_code"])
            errors = bucket["errors_by_code"]  # type: ignore[assignment]
            errors[code] = errors.get(code, 0) + 1
    for stats in bucket["field_matches"].values():  # type: ignore[union-attr]
        stats["accuracy"] = round(stats["matched"] / stats["labeled"], 4) if stats["labeled"] else None
    return bucket


async def main() -> int:
    jobs: dict[str, list[dict[str, object]]] = {}
    for spec in _dataset_specs():
        name = str(spec["name"])
        if name not in TARGETS:
            continue
        fields = list(spec["fields"])  # type: ignore[arg-type]
        items: list[dict[str, object]] = []
        for row in _gold_rows(spec["gold"]):  # type: ignore[arg-type]
            path = _file_from_name(spec["directory"], row.get("파일명", ""))  # type: ignore[arg-type]
            if path is not None:
                items.append({"name": name, "path": path, "expected": row, "fields": fields})
        jobs[name] = items

    semaphore = asyncio.Semaphore(2)
    render_semaphore = asyncio.Semaphore(1)
    datasets: dict[str, object] = {}
    for name, items in jobs.items():
        results: list[dict[str, object]] = []
        for index, item in enumerate(items, start=1):
            results.append(
                await _run_one(item, semaphore=semaphore, render_semaphore=render_semaphore)
            )
            if index % 5 == 0 or index == len(items):
                print(f"{name}: {index}/{len(items)} completed", flush=True)
        datasets[name] = _aggregate(items, results)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            "provider": "same configured RunPod Serverless OCR worker and Korean image model bundle",
            "contract_policy": "PDF baseline plus all-page rendered-PNG retry; rendered-PNG selected for scored fields",
            "purchase_order_policy": "PDF OCR selected only for 공급자 주소; all other selected fields use all-page rendered-PNG OCR",
            "rendering": "all pages; max long side 2200 pixels, reduced to 1100 only above inline payload limit",
            "field_metric": "normalized expected-value containment in selected OCR text; not CER/WER or field-location accuracy",
            "raw_text_persisted": False,
        },
        "datasets": datasets,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, dataset in datasets.items():
        matches = sum(value["matched"] for value in dataset["field_matches"].values())  # type: ignore[union-attr]
        labels = sum(value["labeled"] for value in dataset["field_matches"].values())  # type: ignore[union-attr]
        score = f"{matches / labels * 100:.1f}%" if labels else "not_scored"
        print(f"{name}: {matches}/{labels} = {score}", flush=True)
    return 0 if all(dataset["error_count"] == 0 for dataset in datasets.values()) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
