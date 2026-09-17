"""RunPod OCR dataset evaluation without persisting document text.

The script reports operational RunPod results and field-level exact matches for
datasets that already have a gold XLSX. It deliberately does not invent
business-registration labels or call the embedded PDF text a gold transcript.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import ocr

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "evals" / "ocr-runpod" / "runpod_dataset_summary.json"


def _colnum(cell_ref: str) -> int:
    value = 0
    for char in cell_ref:
        if char.isalpha():
            value = value * 26 + ord(char.upper()) - 64
    return value


def _read_xlsx_rows(path: Path, sheet_index: int = 0) -> list[list[str]]:
    """Read simple XLSX worksheets using the stdlib only."""
    from xml.etree import ElementTree as ET
    from zipfile import ZipFile

    ns = {
        "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    with ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(text.text or "" for text in item.iter(f"{{{ns['a']}}}t"))
                for item in root.findall("a:si", ns)
            ]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relmap = {item.attrib["Id"]: item.attrib["Target"] for item in relationships}
        sheet = list(workbook.find("a:sheets", ns))[sheet_index]
        target = relmap[sheet.attrib[f"{{{ns['r']}}}id"]].lstrip("/")
        target = target if target.startswith("xl/") else "xl/" + target
        root = ET.fromstring(archive.read(target))
        rows: list[list[str]] = []
        for row in root.findall(".//a:sheetData/a:row", ns):
            cells: dict[int, str] = {}
            for cell in row.findall("a:c", ns):
                value = cell.find("a:v", ns)
                if cell.attrib.get("t") == "inlineStr":
                    text = "".join(node.text or "" for node in cell.findall("a:is//a:t", ns))
                elif value is None:
                    text = ""
                elif cell.attrib.get("t") == "s":
                    text = shared[int(value.text or "0")]
                elif cell.attrib.get("t") == "str":
                    text = value.text or ""
                else:
                    text = value.text or ""
                cells[_colnum(cell.attrib["r"])] = text
            if cells:
                rows.append([cells.get(index, "") for index in range(1, max(cells) + 1)])
        return rows


def _gold_rows(path: Path, sheet_index: int = 0) -> list[dict[str, str]]:
    rows = _read_xlsx_rows(path, sheet_index=sheet_index)
    header_index = next(
        index for index, row in enumerate(rows) if row and row[0] in {"문서 ID", "card_id"}
    )
    header = rows[header_index]
    return [
        {header[index]: (row[index] if index < len(row) else "") for index in range(len(header))}
        for row in rows[header_index + 1 :]
        if row and row[0]
    ]


def _normalize(value: object) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).lower()
    return "".join(char for char in value if char.isalnum())


def _clean(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split())


def _expected_value(field: str, value: object) -> str:
    """Expand Excel date serials into a representation OCR can contain."""
    text = _clean(value)
    if re.fullmatch(r"\d+(?:\.0)?", text) and ("일자" in field or "지급일" in field):
        serial = int(float(text))
        date = datetime(1899, 12, 30) + timedelta(days=serial)
        return date.strftime("%Y-%m-%d")
    return text


def _expected_variants(field: str, value: object) -> list[str]:
    text = _expected_value(field, value)
    variants = [_normalize(text)]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        year, month, day = text.split("-")
        variants.append(_normalize(f"{year}년 {int(month)}월 {int(day)}일"))
        variants.append(_normalize(f"{year}.{int(month)}.{int(day)}"))
    return [item for item in variants if item]


def _file_by_number(directory: Path, number: int) -> Path | None:
    for path in sorted(directory.glob("*.pdf")):
        if re.search(rf"(?:^|[_-]){number}\.pdf$", path.name):
            return path
    return None


def _file_from_name(directory: Path, filename: str) -> Path | None:
    exact = directory / filename
    if exact.exists():
        return exact
    match = re.search(r"(\d+)", filename)
    return _file_by_number(directory, int(match.group(1))) if match else None


def _pdf_reference_text(path: Path) -> str:
    try:
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages).strip()
    except Exception:
        return ""


def _edit_distance(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for i, left_item in enumerate(left, 1):
        current = [i]
        for j, right_item in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (left_item != right_item),
                )
            )
        previous = current
    return previous[-1]


def _proxy_error_rates(reference: str, hypothesis: str) -> tuple[int, int, int, int]:
    """Return edit distances and denominators against embedded PDF text.

    This is a diagnostic proxy only. An embedded text layer is not treated as
    a human-reviewed transcription gold set.
    """
    ref_chars = list(_normalize(reference))
    hyp_chars = list(_normalize(hypothesis))
    ref_words = _clean(reference).split()
    hyp_words = _clean(hypothesis).split()
    return (
        _edit_distance(ref_chars, hyp_chars),
        len(ref_chars),
        _edit_distance(ref_words, hyp_words),
        len(ref_words),
    )


def _dataset_specs() -> list[dict[str, object]]:
    return [
        {
            "name": "견적서",
            "directory": ROOT / "data/sample/견적서_50개",
            "gold": ROOT / "data/sample/견적서_50개/견적서_50개_정답지.xlsx",
            "fields": ["고객사명", "견적일자", "견적번호", "총액(VAT 포함)"],
            "profile": "document",
        },
        {
            "name": "계약서",
            "directory": ROOT / "data/sample/계약서_50개",
            "gold": ROOT / "data/sample/계약서_50개/계약서_50개_정답지.xlsx",
            "fields": ["을_상호", "을_대표이사", "갑_상호", "총액(VAT 포함)"],
            "profile": "document",
        },
        {
            "name": "발주서",
            "directory": ROOT / "data/sample/발주서_50개",
            "gold": ROOT / "data/sample/발주서_50개/발주서_50개_정답지.xlsx",
            "fields": [
                "공급자",
                "공급자 사업자번호",
                "공급자 주소",
                "공급자 전화",
                "공급자 FAX",
                "공급자 담당자",
                "발주자",
                "발주자 사업자번호",
                "발주자 주소",
                "발주자 전화",
                "발주자 FAX",
                "발주자 담당자",
                "납품장소",
                "대금 지급조건",
                "총액",
            ],
            "profile": "document",
        },
        {
            "name": "명함",
            "directory": ROOT / "data/sample/실제명함_36개",
            "gold": ROOT / "data/sample/실제명함_36개/실제명함_36개_정답지.xlsx",
            "fields": ["company_name", "name", "phone", "email"],
            "profile": "business_card",
        },
    ]


async def _run_one(item: dict[str, object], semaphore: asyncio.Semaphore) -> dict[str, object]:
    path: Path = item["path"]  # type: ignore[assignment]
    started = time.perf_counter()
    async with semaphore:
        try:
            result = await ocr._runpod(
                file_name=path.name,
                media_type="image/jpeg"
                if path.suffix.lower() in {".jpg", ".jpeg"}
                else "application/pdf",
                content=path.read_bytes(),
                source_url=None,
                profile=str(item["profile"]),
            )
            text = result.plain_text
            expected = item.get("expected", {})
            fields = item.get("fields", [])
            matches = {
                field: bool(
                    any(variant in _normalize(text) for variant in _expected_variants(field, value))
                )
                for field, value in expected.items()
                if field in fields and _clean(value)
            }
            proxy = None
            if path.suffix.lower() == ".pdf":
                reference = _pdf_reference_text(path)
                if reference:
                    proxy = _proxy_error_rates(reference, text)
            return {
                "status": "success",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "field_matches": matches,
                "proxy": proxy,
            }
        except Exception as error:
            return {
                "status": "error",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "error_type": type(error).__name__,
                "error_code": str(error),
            }


async def main() -> int:
    semaphore = asyncio.Semaphore(4)
    jobs: list[dict[str, object]] = []
    dataset_counts: dict[str, int] = {}
    only = {
        item.strip()
        for item in __import__("os").environ.get("RUNPOD_EVAL_ONLY", "").split(",")
        if item.strip()
    }
    for spec in _dataset_specs():
        if only and str(spec["name"]) not in only:
            continue
        directory = spec["directory"]  # type: ignore[assignment]
        gold = spec["gold"]  # type: ignore[assignment]
        rows = _gold_rows(gold)
        fields = list(spec["fields"])  # type: ignore[arg-type]
        count = 0
        for row in rows:
            path = _file_from_name(directory, row.get("파일명", row.get("file_name", "")))
            if path is None:
                continue
            jobs.append(
                {
                    "name": spec["name"],
                    "path": path,
                    "profile": spec["profile"],
                    "fields": fields,
                    "expected": row,
                }
            )
            count += 1
        dataset_counts[str(spec["name"])] = count

    if not only or "사업자등록증" in only:
        business_dir = ROOT / "data/sample/사업자등록증_24개"
        business_files = sorted(
            path
            for path in business_dir.iterdir()
            if path.suffix.lower() in {".pdf", ".jpg", ".jpeg", ".png"}
        )
        for path in business_files:
            # 파일명은 문서 상호와 함께 제공된 약한 라벨이다. 사업자번호·대표자·
            # 주소는 독립적인 골드 라벨이 없어 채점하지 않는다.
            company = re.sub(r"\s*사업자등록증.*$", "", path.stem).strip()
            jobs.append(
                {
                    "name": "사업자등록증",
                    "path": path,
                    "profile": "document",
                    "fields": ["상호(파일명 파생)"],
                    "expected": {"상호(파일명 파생)": company},
                }
            )
        dataset_counts["사업자등록증"] = len(business_files)

    results = await asyncio.gather(*[_run_one(item, semaphore) for item in jobs])
    aggregate: dict[str, dict[str, object]] = {}
    for item, result in zip(jobs, results, strict=True):
        name = str(item["name"])
        bucket = aggregate.setdefault(
            name,
            {
                "input_count": 0,
                "success_count": 0,
                "error_count": 0,
                "field_matches": {},
                "proxy": {
                    "char_distance": 0,
                    "char_reference": 0,
                    "word_distance": 0,
                    "word_reference": 0,
                    "documents": 0,
                },
                "errors": [],
            },
        )
        bucket["input_count"] = int(bucket["input_count"]) + 1
        if result["status"] == "success":
            bucket["success_count"] = int(bucket["success_count"]) + 1
            for field, matched in result.get("field_matches", {}).items():
                stats = bucket["field_matches"].setdefault(field, {"matched": 0, "labeled": 0})  # type: ignore[union-attr]
                stats["labeled"] += 1
                stats["matched"] += int(bool(matched))
            if result.get("proxy"):
                char_distance, char_reference, word_distance, word_reference = result["proxy"]
                proxy_bucket = bucket["proxy"]
                proxy_bucket["char_distance"] += char_distance
                proxy_bucket["char_reference"] += char_reference
                proxy_bucket["word_distance"] += word_distance
                proxy_bucket["word_reference"] += word_reference
                proxy_bucket["documents"] += 1
        else:
            bucket["error_count"] = int(bucket["error_count"]) + 1
            bucket["errors"].append(
                {
                    "file": item["path"].name,
                    "error_type": result.get("error_type"),
                    "error_code": result.get("error_code"),
                }
            )  # type: ignore[union-attr]

    for bucket in aggregate.values():
        for stats in bucket["field_matches"].values():  # type: ignore[union-attr]
            stats["accuracy"] = (
                round(stats["matched"] / stats["labeled"], 4) if stats["labeled"] else None
            )
        proxy = bucket["proxy"]
        proxy["cer_proxy"] = (
            round(proxy["char_distance"] / proxy["char_reference"], 4)
            if proxy["char_reference"]
            else None
        )
        proxy["wer_proxy"] = (
            round(proxy["word_distance"] / proxy["word_reference"], 4)
            if proxy["word_reference"]
            else None
        )

    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "method": {
            "provider": "RunPod Serverless via backend OCR adapter",
            "field_metric": (
                "normalized expected-value containment in OCR plain text; not field-location "
                "accuracy"
            ),
            "proxy_metric": (
                "CER/WER against embedded PDF text layer only; not human-reviewed gold "
                "transcription"
            ),
            "business_registration_fields": (
                "filename-derived company label only; independent "
                "registration-number/representative/address gold labels are "
                "absent"
            ),
            "raw_text_persisted": False,
        },
        "dataset_counts": dataset_counts,
        "datasets": aggregate,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if all(item["error_count"] == 0 for item in aggregate.values()) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
