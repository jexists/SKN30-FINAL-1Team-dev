"""Evaluate rendered-PNG RunPod OCR against the saved PDF-path baseline.

The script stores only aggregate field matches and processing counts. It never
writes OCR text or document contents to the evaluation result.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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
BASELINE = ROOT / "output/evals/ocr-runpod/runpod_dataset_summary.json"
OUT = ROOT / "output/evals/ocr-png-fallback-ab/runpod_png_fallback_ab_summary.json"
TARGETS = {"계약서", "발주서"}
FAILED_BUSINESS_LICENSES = [
    "그린스토어 사업자등록증.png",
    "다울영농조합법인 사업자등록증.png",
    "으뜸방재 ENG 사업자등록증.png",
]


def _field_matches(text: str, expected: dict[str, str], fields: list[str]) -> dict[str, bool]:
    normalized = _normalize(text)
    return {
        field: bool(any(variant in normalized for variant in _expected_variants(field, value)))
        for field, value in expected.items()
        if field in fields and _clean(value)
    }


async def _run_rendered_pdf(
    item: dict[str, object], semaphore: asyncio.Semaphore, render_semaphore: asyncio.Semaphore
) -> dict[str, object]:
    path: Path = item["path"]  # type: ignore[assignment]
    started = time.perf_counter()
    try:
        # pypdfium2 렌더러는 동시 스레드 사용 시 네이티브 프로세스가 종료될 수 있어
        # 렌더링만 직렬화한다. RunPod OCR 요청은 아래 semaphore로 2건까지 병렬 실행한다.
        async with render_semaphore:
            pages = await asyncio.to_thread(ocr.render_pdf_pages_png, path.read_bytes())
        markdown_pages: list[str] = []
        for page_number, png in enumerate(pages, start=1):
            async with semaphore:
                result = await ocr._runpod(
                    file_name=f"{path.stem}-page-{page_number}.png",
                    media_type="image/png",
                    content=png,
                    source_url=None,
                    profile="document",
                )
            markdown_pages.append(result.plain_text)
        text = "\n".join(markdown_pages)
        return {
            "path_key": str(path),
            "status": "success",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "page_count": len(pages),
            "field_matches": _field_matches(
                text,
                item["expected"],
                item["fields"],  # type: ignore[arg-type]
            ),
        }
    except Exception as error:
        return {
            "path_key": str(path),
            "status": "error",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "error_code": str(error),
        }


def _prepared_business_license(content: bytes) -> bytes:
    """실패한 PNG를 RGB PNG로 재인코딩해 투명도·팔레트 문제를 제거한다."""
    from io import BytesIO

    with Image.open(BytesIO(content)) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((2400, 2400))
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()


async def _retry_business_license(path: Path, semaphore: asyncio.Semaphore) -> dict[str, object]:
    started = time.perf_counter()
    try:
        content = await asyncio.to_thread(_prepared_business_license, path.read_bytes())
        async with semaphore:
            await ocr._runpod(
                file_name=path.name,
                media_type="image/png",
                content=content,
                source_url=None,
                profile="document",
            )
        return {"status": "success", "elapsed_seconds": round(time.perf_counter() - started, 3)}
    except Exception as error:
        return {
            "status": "error",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "error_code": str(error),
        }


def _aggregate(
    items: list[dict[str, object]], results: list[dict[str, object]]
) -> dict[str, object]:
    bucket: dict[str, object] = {
        "input_count": len(items),
        "success_count": 0,
        "error_count": 0,
        "processed_pages": 0,
        "field_matches": {},
        "errors_by_code": {},
    }
    for _item, result in zip(items, results, strict=True):
        if result["status"] == "success":
            bucket["success_count"] = int(bucket["success_count"]) + 1
            bucket["processed_pages"] = int(bucket["processed_pages"]) + int(result["page_count"])
            for field, matched in result["field_matches"].items():  # type: ignore[union-attr]
                stats = bucket["field_matches"].setdefault(field, {"matched": 0, "labeled": 0})  # type: ignore[union-attr]
                stats["matched"] += int(bool(matched))
                stats["labeled"] += 1
        else:
            bucket["error_count"] = int(bucket["error_count"]) + 1
            code = str(result["error_code"])
            errors = bucket["errors_by_code"]  # type: ignore[assignment]
            errors[code] = errors.get(code, 0) + 1
    for stats in bucket["field_matches"].values():  # type: ignore[union-attr]
        stats["accuracy"] = (
            round(stats["matched"] / stats["labeled"], 4) if stats["labeled"] else None
        )
    return bucket


async def main() -> int:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    items_by_name: dict[str, list[dict[str, object]]] = {}
    for spec in _dataset_specs():
        name = str(spec["name"])
        if name not in TARGETS:
            continue
        rows = _gold_rows(spec["gold"])  # type: ignore[arg-type]
        fields = list(spec["fields"])  # type: ignore[arg-type]
        items: list[dict[str, object]] = []
        for row in rows:
            path = _file_from_name(spec["directory"], row.get("파일명", ""))  # type: ignore[arg-type]
            if path:
                items.append({"path": path, "expected": row, "fields": fields})
        items_by_name[name] = items

    semaphore = asyncio.Semaphore(2)
    render_semaphore = asyncio.Semaphore(1)
    candidate: dict[str, object] = {}
    for name, items in items_by_name.items():
        completed_by_path: dict[str, dict[str, object]] = {}
        tasks = [
            asyncio.create_task(_run_rendered_pdf(item, semaphore, render_semaphore))
            for item in items
        ]
        for completed, task in enumerate(asyncio.as_completed(tasks), start=1):
            result = await task
            completed_by_path[str(result["path_key"])] = result
            if completed % 5 == 0 or completed == len(tasks):
                print(f"{name}: {completed}/{len(tasks)} completed", flush=True)
        ordered_results = [completed_by_path[str(item["path"])] for item in items]
        candidate[name] = _aggregate(items, ordered_results)

    business_dir = ROOT / "data/sample/사업자등록증_24개"
    retry_paths = [business_dir / name for name in FAILED_BUSINESS_LICENSES]
    retry_results = await asyncio.gather(
        *[_retry_business_license(path, semaphore) for path in retry_paths]
    )
    print(f"사업자등록증 재시도: {len(retry_results)}/{len(retry_results)} completed", flush=True)

    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "method": {
            "comparison": "saved RunPod PDF-path baseline versus rendered PNG image-path candidate",
            "provider": (
                "same RunPod Serverless OCR worker and same configured Korean image model "
                "bundle"
            ),
            "rendering": (
                "all PDF pages, maximum long side 2200 pixels; reduced to 1100 pixels only when "
                "inline payload limit is "
                "exceeded"
            ),
            "concurrency": 2,
            "field_metric": (
                "normalized expected-value containment in combined OCR text; not field-location "
                "accuracy"
            ),
            "raw_text_persisted": False,
        },
        "baseline": {name: baseline["datasets"][name] for name in TARGETS},
        "candidate": candidate,
        "business_license_retry": {
            "input_count": len(retry_results),
            "success_count": sum(result["status"] == "success" for result in retry_results),
            "error_count": sum(result["status"] != "success" for result in retry_results),
            "preprocess": (
                "EXIF transpose, RGB conversion, maximum long side 2400 pixels, PNG "
                "re-encode"
            ),
            "errors_by_code": {
                code: sum(result.get("error_code") == code for result in retry_results)
                for code in sorted(
                    {
                        str(result.get("error_code"))
                        for result in retry_results
                        if result.get("error_code")
                    }
                )
            },
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"aggregate written: {OUT.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
