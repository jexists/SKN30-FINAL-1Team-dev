"""Create a page-level human transcription manifest for formal OCR CER/WER."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/evals/ocr-cer-wer/raw"
MANIFEST = OUT / "gold_transcription_template.csv"
PROTOCOL = OUT / "review_protocol.md"


def _page_count(path: Path) -> int:
    if path.suffix.lower() == ".pdf":
        return len(PdfReader(str(path)).pages)
    return 1


def _sources() -> list[tuple[str, Path]]:
    specs = [
        ("계약서", ROOT / "data/sample/계약서_50개"),
        ("발주서", ROOT / "data/sample/발주서_50개"),
        ("사업자등록증", ROOT / "data/sample/사업자등록증_24개"),
    ]
    allowed = {".pdf", ".png", ".jpg", ".jpeg"}
    return [
        (document_type, path)
        for document_type, directory in specs
        for path in sorted(directory.iterdir())
        if path.suffix.lower() in allowed
    ]


def _protocol(total_pages: int) -> str:
    return f"""# 정식 OCR CER/WER 전사 골드셋 검수 지침

## 범위

- 대상: 계약서·발주서·사업자등록증 원본 {total_pages}페이지
- 단위: `sample_id` 한 행당 원본의 한 페이지
- 원칙: OCR 결과를 보지 않고 원본 화면만 보고 전사한다.

## 단일 검수자 2회 전사와 확정

1. 1차 전사를 끝낸 뒤 최소 하루 간격을 두고, 1차 전사 내용을 보지 않은 채 2차 전사를 한다.
2. 두 전사가 다르면 원본을 다시 보고 `adjudicated_text`에 확정 전사를 입력한다.
3. `status`는 `approved`로, `approver`와 `approved_at`은 실제 검수 정보를 입력한다.
4. 빈 페이지도 `approved`로 확정하고 전사 칸은 빈 문자열로 둔다.

## 전사 규칙

- 보이는 문자·숫자·기호·표기 순서를 보존한다.
- 줄바꿈은 유지할 수 있으나 CER 계산 시 공백 하나로 정규화한다.
- 읽을 수 없는 글자는 임의 추정하지 않고 `□`로 표기한다.
- 표는 위에서 아래, 왼쪽에서 오른쪽 순으로 전사한다.
- 도장·서명은 판독 가능한 문자만 전사하고, 판독 불가 그림은 제외한다.

## 계산 전 확인

- 이 파일은 개인정보를 포함할 수 있으므로 로컬에서만 보관하고 Git에 추가하지 않는다.
- 모든 행이 `approved`가 아니면 점수 계산기는 정식 CER/WER 산출을 거부한다.
"""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    for document_type, path in _sources():
        for page_number in range(1, _page_count(path) + 1):
            sample_id = f"{document_type}:{path.stem}:{page_number:03d}"
            rows.append(
                {
                    "sample_id": sample_id,
                    "document_type": document_type,
                    "source_path": str(path.relative_to(ROOT)),
                    "page_number": str(page_number),
                    "reviewer_a_text": "",
                    "reviewer_b_text": "",
                    "adjudicated_text": "",
                    "status": "pending",
                    "approver": "",
                    "approved_at": "",
                }
            )
    with MANIFEST.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    PROTOCOL.write_text(_protocol(len(rows)), encoding="utf-8")
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "page_count": len(rows),
        "document_counts": {
            document_type: sum(row["document_type"] == document_type for row in rows)
            for document_type in ("계약서", "발주서", "사업자등록증")
        },
        "manifest": str(MANIFEST.relative_to(ROOT)),
        "protocol": str(PROTOCOL.relative_to(ROOT)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
