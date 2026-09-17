"""Score approved human OCR transcriptions using corpus CER and WER.

The inputs stay in an ignored local directory because they can contain personal
information. The emitted JSON contains aggregate counts and scores only.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "output/evals/ocr-cer-wer/raw"
GOLD = RAW / "gold_transcriptions.csv"
HYPOTHESES = RAW / "ocr_hypotheses.csv"
OUT = ROOT / "output/evals/ocr-cer-wer/cer_wer_summary.json"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _normalize(text: str) -> str:
    """Keep characters and punctuation; only normalize Unicode and whitespace."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).strip())


def _edit_distance(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for index, left_item in enumerate(left, start=1):
        current = [index]
        for right_index, right_item in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_item != right_item),
                )
            )
        previous = current
    return previous[-1]


def _score(pairs: list[tuple[str, str]]) -> dict[str, int | float]:
    char_distance = char_reference = word_distance = word_reference = 0
    for gold, hypothesis in pairs:
        normalized_gold = _normalize(gold)
        normalized_hypothesis = _normalize(hypothesis)
        char_distance += _edit_distance(list(normalized_gold), list(normalized_hypothesis))
        char_reference += len(normalized_gold)
        gold_words = normalized_gold.split()
        hypothesis_words = normalized_hypothesis.split()
        word_distance += _edit_distance(gold_words, hypothesis_words)
        word_reference += len(gold_words)
    return {
        "page_count": len(pairs),
        "char_distance": char_distance,
        "char_reference": char_reference,
        "cer": round(char_distance / char_reference, 6) if char_reference else None,
        "word_distance": word_distance,
        "word_reference": word_reference,
        "wer": round(word_distance / word_reference, 6) if word_reference else None,
    }


def main() -> int:
    if not GOLD.exists() or not HYPOTHESES.exists():
        missing = [str(path.relative_to(ROOT)) for path in (GOLD, HYPOTHESES) if not path.exists()]
        raise SystemExit(f"missing_required_input:{','.join(missing)}")
    gold_rows = _read_csv(GOLD)
    hypothesis_rows = _read_csv(HYPOTHESES)
    pending = [row.get("sample_id", "") for row in gold_rows if row.get("status") != "approved"]
    if pending:
        raise SystemExit(f"gold_not_approved:{len(pending)}")
    gold_by_id = {row.get("sample_id", ""): row for row in gold_rows}
    hypotheses_by_id = {row.get("sample_id", ""): row for row in hypothesis_rows}
    missing_hypotheses = sorted(set(gold_by_id) - set(hypotheses_by_id))
    if missing_hypotheses:
        raise SystemExit(f"sample_id_mismatch:missing_hypotheses={len(missing_hypotheses)}")
    pairs_by_type: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for sample_id, gold_row in gold_by_id.items():
        gold_text = gold_row.get("adjudicated_text", "")
        if not gold_text and (gold_row.get("reviewer_a_text") or gold_row.get("reviewer_b_text")):
            gold_text = gold_row.get("reviewer_a_text") or gold_row.get("reviewer_b_text", "")
        pairs_by_type[gold_row.get("document_type", "미분류")].append(
            (gold_text, hypotheses_by_id[sample_id].get("ocr_text", ""))
        )
    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "method": {
            "gold": "human-reviewed page-level transcription; all pages status=approved",
            "normalization": (
                "Unicode NFKC and whitespace collapse only; characters and punctuation "
                "retained"
            ),
            "cer": "corpus character edit distance divided by corpus reference characters",
            "wer": "corpus whitespace-token edit distance divided by corpus reference tokens",
            "raw_text_persisted": False,
        },
        "sample": {
            "gold_page_count": len(gold_rows),
            "available_hypothesis_page_count": len(hypothesis_rows),
            "document_counts": {
                document_type: sum(row.get("document_type") == document_type for row in gold_rows)
                for document_type in sorted(
                    {row.get("document_type", "미분류") for row in gold_rows}
                )
            },
        },
        "overall": _score([pair for pairs in pairs_by_type.values() for pair in pairs]),
        "by_document_type": {name: _score(pairs) for name, pairs in sorted(pairs_by_type.items())},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
