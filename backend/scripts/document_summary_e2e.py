"""실제 문서를 추출·요약·청크화하는 OpenAI E2E 점검 도구.

외부 전송은 명시적으로 ``--send-to-llm``을 지정한 경우에만 수행한다.
원문과 요약 본문은 출력하지 않고 처리 지표만 출력한다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents import document_summary
from app.services import ocr
from app.services.document_extraction import ExtractionError, extract_document
from app.services.document_processing import _summary_markdown

MEDIA_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}


def _extract(path: Path):
    media_type = MEDIA_TYPES[path.suffix.lower()]
    content = path.read_bytes()
    try:
        return extract_document(file_name=path.name, media_type=media_type, content=content)
    except ExtractionError as error:
        if str(error) != "ocr_required":
            raise
        return asyncio.run(
            ocr.extract_document(file_name=path.name, media_type=media_type, content=content)
        )


def evaluate(path: Path) -> dict[str, object]:
    if path.suffix.lower() not in MEDIA_TYPES:
        return {"file": path.name, "status": "unsupported_extension"}
    try:
        extracted = _extract(path)
        summary = asyncio.run(
            document_summary.run(
                document_summary.input_snapshot(
                    file_name=path.name,
                    media_type=MEDIA_TYPES[path.suffix.lower()],
                    extracted=extracted,
                )
            )
        )
        chunk_rows = document_summary.chunks(
            extracted.markdown,
            pages=extracted.payload.get("pages"),
        )
        summary_markdown = _summary_markdown(summary)
        artifacts_ready = all(
            (
                extracted.plain_text,
                extracted.markdown,
                extracted.payload,
                summary_markdown,
                json.dumps(summary.model_dump(), ensure_ascii=False),
            )
        )
        pages = extracted.payload.get("pages", [])
        page_numbers = [page.get("page_number") for page in pages if isinstance(page, dict)]
        return {
            "file": path.name,
            "status": "passed" if artifacts_ready else "artifact_incomplete",
            "source_type": extracted.payload.get("source_type"),
            "pages": len(pages) if isinstance(pages, list) else 0,
            "page_numbers_valid": page_numbers == list(range(1, len(page_numbers) + 1)),
            "text_chars": len(extracted.plain_text),
            "chunks": len(chunk_rows),
            "summary_received": bool(summary.summary),
            "key_points": len(summary.key_points),
            "risk_flags": len(summary.risk_flags),
            "extracted_field_count": len(summary.extracted_fields),
            "artifacts_ready": artifacts_ready,
        }
    except Exception as error:
        return {"file": path.name, "status": "failed", "error_type": type(error).__name__}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--send-to-llm",
        action="store_true",
        help="실제 문서 원문을 설정된 LLM API로 전송한다.",
    )
    args = parser.parse_args()
    if not args.send_to_llm:
        parser.error("실제 외부 전송에는 --send-to-llm을 명시해야 합니다.")
    results = [evaluate(path) for path in args.paths]
    print(json.dumps(results, ensure_ascii=False))
    if any(item["status"] != "passed" for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
