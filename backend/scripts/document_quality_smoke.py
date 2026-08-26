"""실제 문서의 로컬 추출·OCR·청크 구조를 개인정보 없이 점검한다.

이 스크립트는 LLM이나 외부 API를 호출하지 않는다. 파일명과 품질 지표만 출력한다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.document_summary import chunks
from app.services import ocr
from app.services.document_extraction import ExtractionError, extract_document

MEDIA_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".html": "text/html",
    ".htm": "text/html",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def _paths(values: list[Path] | None) -> list[Path]:
    if values:
        return [path for value in values for path in _expand(value)]
    default = Path(__file__).resolve().parents[2] / "data" / "sanitized_docs"
    return sorted(path for path in default.iterdir() if path.is_file())


def _expand(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(item for item in path.iterdir() if item.is_file())
    return [path]


def _page_numbers_valid(pages: object) -> bool:
    if not isinstance(pages, list) or not pages:
        return False
    numbers = [page.get("page_number") for page in pages if isinstance(page, dict)]
    return numbers == list(range(1, len(numbers) + 1))


def _extract(path: Path, *, use_local_ocr: bool):
    media_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    content = path.read_bytes()
    if media_type.startswith("image/"):
        if not use_local_ocr:
            raise ExtractionError("ocr_required")
        return asyncio.run(
            ocr.extract_document(file_name=path.name, media_type=media_type, content=content)
        )
    try:
        return extract_document(file_name=path.name, media_type=media_type, content=content)
    except ExtractionError as error:
        if not use_local_ocr or str(error) != "ocr_required":
            raise
        return asyncio.run(
            ocr.extract_document(file_name=path.name, media_type=media_type, content=content)
        )


def evaluate(path: Path, *, use_local_ocr: bool) -> dict[str, object]:
    if path.suffix.lower() not in MEDIA_TYPES:
        return {"file": path.name, "status": "unsupported_extension"}
    try:
        result = _extract(path, use_local_ocr=use_local_ocr)
    except Exception as error:
        return {"file": path.name, "status": "failed", "error_type": type(error).__name__}

    pages = result.payload.get("pages", [])
    chunk_rows = chunks(result.markdown, pages=pages)
    return {
        "file": path.name,
        "status": "passed",
        "source_type": result.payload.get("source_type"),
        "pages": len(pages) if isinstance(pages, list) else 0,
        "page_numbers_valid": _page_numbers_valid(pages),
        "text_chars": len(result.plain_text),
        "markdown_chars": len(result.markdown),
        "nonempty_chunks": sum(bool(item.get("content", "").strip()) for item in chunk_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument(
        "--ocr-local",
        action="store_true",
        help="ocr_required 파일을 설정된 로컬 OCR Provider로 재시도한다.",
    )
    args = parser.parse_args()
    results = [evaluate(path, use_local_ocr=args.ocr_local) for path in _paths(args.paths)]
    print(json.dumps(results, ensure_ascii=False))
    if not results or any(item["status"] != "passed" for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
