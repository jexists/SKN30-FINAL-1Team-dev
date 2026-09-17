"""Capture page-level OCR hypotheses locally for a prepared CER/WER gold set."""

from __future__ import annotations

import asyncio
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import ocr


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "output/evals/ocr-cer-wer/raw"
MANIFEST = RAW / "gold_transcription_template.csv"
HYPOTHESES = RAW / "ocr_hypotheses.csv"
SUMMARY = ROOT / "output/evals/ocr-cer-wer/hypothesis_capture_summary.json"


def _media_type(path: Path) -> str:
    return {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }[path.suffix.lower()]


def _manifest() -> tuple[list[dict[str, str]], dict[Path, list[dict[str, str]]]]:
    with MANIFEST.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_path: dict[Path, list[dict[str, str]]] = {}
    for row in rows:
        by_path.setdefault(ROOT / row["source_path"], []).append(row)
    for entries in by_path.values():
        entries.sort(key=lambda row: int(row["page_number"]))
    return rows, by_path


def _load_existing() -> dict[str, dict[str, str]]:
    if not HYPOTHESES.exists():
        return {}
    with HYPOTHESES.open(encoding="utf-8", newline="") as handle:
        return {row["sample_id"]: row for row in csv.DictReader(handle) if row.get("sample_id")}


def _write_checkpoint(rows: dict[str, dict[str, str]]) -> None:
    """Persist completed OCR pages so an interrupted run can resume safely."""
    HYPOTHESES.parent.mkdir(parents=True, exist_ok=True)
    temporary = HYPOTHESES.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample_id", "ocr_text"])
        writer.writeheader()
        writer.writerows(rows[sample_id] for sample_id in sorted(rows))
    temporary.replace(HYPOTHESES)


async def _capture_one(
    path: Path, rows: list[dict[str, str]], semaphore: asyncio.Semaphore
) -> dict[str, object]:
    async with semaphore:
        try:
            result = await ocr.extract_document(
                file_name=path.name,
                media_type=_media_type(path),
                content=path.read_bytes(),
                profile="document",
            )
            pages = result.payload.get("pages")
            if not isinstance(pages, list) or len(pages) != len(rows):
                return {"status": "error", "error_code": "page_count_mismatch"}
            output: list[dict[str, str]] = []
            for manifest_row, page in zip(rows, pages):
                text = page.get("markdown") if isinstance(page, dict) else None
                if not isinstance(text, str):
                    return {"status": "error", "error_code": "page_markdown_missing"}
                output.append({"sample_id": manifest_row["sample_id"], "ocr_text": text})
            return {"status": "success", "rows": output}
        except Exception as error:
            return {"status": "error", "error_code": str(error)}


async def main() -> int:
    if not MANIFEST.exists():
        raise SystemExit(f"missing_manifest:{MANIFEST.relative_to(ROOT)}")
    manifest_rows, by_path = _manifest()
    captured_by_id = _load_existing()
    expected_ids = {row["sample_id"] for row in manifest_rows}
    captured_by_id = {
        sample_id: row for sample_id, row in captured_by_id.items() if sample_id in expected_ids
    }
    existing_page_count = len(captured_by_id)
    pending_by_path = {
        path: rows
        for path, rows in by_path.items()
        if any(row["sample_id"] not in captured_by_id for row in rows)
    }
    semaphore = asyncio.Semaphore(2)
    jobs = [
        asyncio.create_task(_capture_one(path, rows, semaphore))
        for path, rows in pending_by_path.items()
    ]
    errors: Counter[str] = Counter()
    for completed, task in enumerate(asyncio.as_completed(jobs), start=1):
        result = await task
        if result["status"] == "success":
            for row in result["rows"]:  # type: ignore[union-attr]
                captured_by_id[row["sample_id"]] = row
            _write_checkpoint(captured_by_id)
        else:
            errors[str(result["error_code"])] += 1
        if completed % 10 == 0 or completed == len(jobs):
            print(
                f"documents: {completed}/{len(jobs)} completed; pages: {len(captured_by_id)}/{len(expected_ids)}",
                flush=True,
            )
    captured_ids = set(captured_by_id)
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            "provider": "configured backend OCR adapter with conditional RunPod PDF-to-PNG retry",
            "max_document_concurrency": 2,
            "raw_hypotheses": str(HYPOTHESES.relative_to(ROOT)),
            "raw_hypotheses_gitignored": True,
        },
        "input_documents": len(by_path),
        "resumed_pages": existing_page_count,
        "processed_documents_this_run": len(jobs),
        "expected_pages": len(expected_ids),
        "captured_pages": len(captured_ids),
        "error_document_count": sum(errors.values()),
        "errors_by_code": dict(errors),
    }
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not errors and captured_ids == expected_ids else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
