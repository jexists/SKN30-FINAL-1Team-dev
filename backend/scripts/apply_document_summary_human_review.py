"""브라우저에서 내려받은 문서요약 사람검수 결과를 골든셋 사본에 반영한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DECISIONS = {"pass", "revise", "hold", "pending"}


def _case_ids(golden: dict[str, Any]) -> set[str]:
    return {
        case["case_id"]
        for key in ("summary_cases", "rag_cases")
        for case in golden.get(key, [])
    }


def apply_review(golden: dict[str, Any], review_export: dict[str, Any]) -> dict[str, Any]:
    review = review_export.get("human_review")
    if not isinstance(review, dict):
        raise ValueError("human_review_missing")
    unknown = set(review) - _case_ids(golden)
    if unknown:
        raise ValueError(f"unknown_case_ids:{sorted(unknown)}")
    invalid = {
        case_id: state.get("decision")
        for case_id, state in review.items()
        if not isinstance(state, dict) or state.get("decision") not in DECISIONS
    }
    if invalid:
        raise ValueError(f"invalid_review_decisions:{invalid}")
    all_case_ids = _case_ids(golden)
    missing = all_case_ids - set(review)
    if missing:
        raise ValueError(f"missing_case_ids:{sorted(missing)}")
    decisions = {
        case_id: {
            "decision": state["decision"],
            "note": str(state.get("note") or ""),
        }
        for case_id, state in review.items()
    }
    decision_values = {item["decision"] for item in decisions.values()}
    if "revise" in decision_values:
        status = "needs_revision"
    elif "hold" in decision_values or "pending" in decision_values:
        status = "pending"
    else:
        status = "approved"
    reviewed = dict(golden)
    reviewed["human_review"] = {
        "status": status,
        "reviewed_case_ids": sorted(decisions),
        "decisions": decisions,
        "source": "document-summary-human-review.json",
        "exported_at": review_export.get("exported_at"),
    }
    return reviewed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    golden = json.loads(args.golden.read_text(encoding="utf-8"))
    review_export = json.loads(args.review.read_text(encoding="utf-8"))
    reviewed = apply_review(golden, review_export)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(reviewed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    decisions = reviewed["human_review"]["decisions"]
    counts = {
        decision: sum(item["decision"] == decision for item in decisions.values())
        for decision in sorted(DECISIONS)
    }
    print(
        json.dumps(
            {
                "status": "created",
                "review_status": reviewed["human_review"]["status"],
                "counts": counts,
                "path": str(args.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
