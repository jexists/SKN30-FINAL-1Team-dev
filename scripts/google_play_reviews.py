#!/usr/bin/env python3
"""Collect public Google Play reviews locally and export aggregate-only statistics."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from collections import Counter
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlencode
from urllib.request import Request, urlopen


RPC_ID = "UsvDTd"
ENDPOINT = "https://play.google.com/_/PlayStoreUi/data/batchexecute"
LANGUAGE_STREAMS = (
    "en", "af", "am", "ar", "as", "az", "be", "bg", "bn", "bs", "ca", "cs", "da",
    "de", "el", "es", "et", "eu", "fa", "fi", "fil", "fr", "gl", "gsw", "gu", "he",
    "hi", "hr", "hu", "hy", "id", "is", "it", "ja", "ka", "kk", "km", "kn", "ko",
    "ky", "ln", "lo", "lt", "lv", "mk", "ml", "mn", "mr", "ms", "my", "ne", "nl",
    "no", "or", "pa", "pl", "pt", "ro", "ru", "si", "sk", "sl", "sq", "sr", "sv",
    "sw", "ta", "te", "th", "tr", "uk", "ur", "uz", "vi", "zh-CN", "zh-TW", "zu",
)
THEMES = {
    "reliability_performance": re.compile(
        r"\bslow\w*|\blag\w*|\bload\w*|\bcrash\w*|\bfreez\w*|\bfrozen\b|\bglitch\w*|"
        r"\bbug\w*|\berror\w*|blank (?:white )?screen|white screen|\bstuck\b|\bhang(?:s|ing)?\b|"
        r"unresponsive|doesn['’]?t work|does not work|not working|won['’]?t (?:open|load|work)|"
        r"never (?:open|load|work)s?|\bbroken\b|\bunusable\b|force close|clear (?:the )?cache|"
        r"restart|reinstall",
        re.I,
    ),
    "authentication_access": re.compile(
        r"\blog[ -]?in\b|\blogging in\b|\blogged (?:in|out)\b|\bsign[ -]?in\b|password|authenticat|"
        r"verification|verify|\bmfa\b|\b2fa\b|passcode|passkey|custom domain|session|locked out|"
        r"stay logged|kicked out",
        re.I,
    ),
    "ux_navigation": re.compile(
        r"user[ -]?friendly|not intuitive|unintuitive|confus\w*|complicat\w*|difficult|hard to use|"
        r"clunky|\bnavigation\b|\bnavigate\w*|back button|too many clicks|\bmenu\w*|\binterface\b|"
        r"\bui\b|\bux\b|\blayout\b|small screen|\bscroll\w*|landscape|portrait|hard to find",
        re.I,
    ),
    "missing_mobile_capability": re.compile(
        r"desktop version|web version|browser version|mobile web|full site|\blimited\b|"
        r"lack(?:s|ing)? (?:basic )?(?:feature|function)|missing (?:feature|function|tab|button|option)|"
        r"no access to|no ability to|can['’]?t (?:add|edit|create|upload|download)|"
        r"cannot (?:add|edit|create|upload|download)|\breports?\b|\bdashboards?\b|\bsetup\b|landscape",
        re.I,
    ),
    "data_sync_entry": re.compile(
        r"\bsync\w*|\bsav(?:e|es|ed|ing)\b|data (?:loss|lost|missing)|records? (?:missing|disappear)|"
        r"\brefresh\w*|update (?:a |the )?(?:record|data|account|case|opportunit)|enter(?:ing)? data|"
        r"data entry|\binput\b|\bedit(?:ing)?\b|\boffline\b|no internet|network|connectivity|connection",
        re.I,
    ),
    "search_list_filter": re.compile(
        r"\bsearch\w*|\bfilter\w*|\bsort(?:ing)?\b|list view|can['’]?t find|cannot find|hard to find|"
        r"lists? (?:don['’]?t|doesn['’]?t|not|won['’]?t)",
        re.I,
    ),
    "files_media": re.compile(
        r"\bfiles?\b|\bphotos?\b|\bimages?\b|\battachments?\b|\bupload\w*|\bcamera\b|\bpdf\b|"
        r"\bdocuments?\b",
        re.I,
    ),
    "notifications": re.compile(r"\bnotifications?\b|\balerts?\b|\breminders?\b|push notification", re.I),
    "update_regression": re.compile(
        r"latest update|last update|recent update|after (?:the )?update|since (?:the )?update|new version|"
        r"used to work|worked before|update (?:has )?(?:broke|broken|ruined)|update.*not (?:work|load)",
        re.I,
    ),
    "field_work_context": re.compile(
        r"\bfield\b|on the go|clock(?:ing)? in|clock(?:ing)? out|punch(?:ing)? (?:in|out)|time ?sheet|"
        r"check[ -]?in|\bvisits?\b|\bcustomers?\b|sales rep|field rep|\baccounts?\b|"
        r"\bopportunit(?:y|ies)\b|work orders?",
        re.I,
    ),
}
AGGREGATE_FIELDS = (
    "section", "segment", "metric", "value", "unit", "denominator", "period_start_utc",
    "period_end_utc", "note", "source_sha256",
)


def utc_iso(timestamp: list[int] | None) -> str | None:
    if not timestamp:
        return None
    seconds, nanos = timestamp
    return datetime.fromtimestamp(seconds + nanos / 1_000_000_000, timezone.utc).isoformat()


def parse_review(item: list, language: str, app_id: str, collected_at: str) -> dict:
    if not isinstance(item, list) or len(item) < 11:
        raise ValueError("unexpected review payload")
    reply = item[7] if isinstance(item[7], list) else None
    review = {
        "reviewId": item[0],
        "content": item[4] or "",
        "score": item[2],
        "thumbsUpCount": item[6] or 0,
        "reviewCreatedVersion": item[10],
        "reviewedAt": utc_iso(item[5]),
        "hasDeveloperReply": bool(reply),
        "repliedAt": utc_iso(reply[2]) if reply and len(reply) > 2 else None,
        "languageStreams": [language],
        "collectedAtUtc": collected_at,
        "sourceUrl": f"https://play.google.com/store/apps/details?id={app_id}",
        "appId": app_id,
        "sort": "NEWEST",
    }
    if not isinstance(review["reviewId"], str) or review["score"] not in range(1, 6):
        raise ValueError("invalid review id or rating")
    return review


def parse_rpc_response(text: str) -> tuple[list[list], str | None]:
    if text.startswith(")]}'"):
        text = text.split("\n", 1)[1].lstrip()
    envelope = json.loads(text)
    row = next(
        (value for value in envelope if isinstance(value, list) and len(value) > 2 and value[:2] == ["wrb.fr", RPC_ID]),
        None,
    )
    if not row or not row[2]:
        raise ValueError("Google Play returned no review payload")
    payload = json.loads(row[2])
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        raise ValueError("unexpected Google Play response")
    token = payload[1][1] if len(payload) > 1 and payload[1] and len(payload[1]) > 1 else None
    return payload[0], token


def fetch_page(app_id: str, language: str, token: str | None, page_size: int, timeout: int, retries: int) -> tuple[list[list], str | None]:
    argument = [None, None, [2, 2, [page_size, None, token], None, []], [app_id, 7]]
    envelope = [[[RPC_ID, json.dumps(argument, separators=(",", ":")), None, "generic"]]]
    query = urlencode({"rpcids": RPC_ID, "hl": language, "gl": "US"})
    request = Request(
        f"{ENDPOINT}?{query}",
        data=urlencode({"f.req": json.dumps(envelope, separators=(",", ":"))}).encode(),
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "User-Agent": "Mozilla/5.0",
        },
    )
    error: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=timeout) as response:
                return parse_rpc_response(response.read().decode())
        except Exception as exc:  # Network and private-RPC failures share the same bounded retry path.
            error = exc
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    raise RuntimeError(f"review request failed for {language}: {type(error).__name__}") from error


def spreadsheet_safe(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_review_files(jsonl_path: Path, csv_path: Path, rows: list[dict]) -> None:
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = jsonl_path.with_name(f".{jsonl_path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(jsonl_path)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = csv_path.with_name(f".{csv_path.name}.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=("리뷰내용", "별점"), lineterminator="\n")
        writer.writeheader()
        writer.writerows({"리뷰내용": spreadsheet_safe(row["content"]), "별점": row["score"]} for row in rows)
    temporary.replace(csv_path)


def crawl(args: argparse.Namespace) -> None:
    if not 1 <= args.page_size <= 4500:
        raise SystemExit("--page-size must be between 1 and 4500")
    collected_at = datetime.now(timezone.utc).isoformat()
    reviews: dict[str, dict] = {}
    stream_stats: dict[str, dict] = {}
    raw_assignments = 0
    manifest = {
        "schemaVersion": 1,
        "appId": args.app_id,
        "rpcId": RPC_ID,
        "sort": "NEWEST",
        "collectedAtUtc": collected_at,
        "pageSize": args.page_size,
        "languageStreamsAttempted": args.languages,
        "streams": stream_stats,
        "failures": [],
    }
    try:
        for language in args.languages:
            token = None
            seen_tokens: set[str] = set()
            pages = returned = 0
            while True:
                batch, next_token = fetch_page(
                    args.app_id, language, token, args.page_size, args.timeout, args.retries
                )
                pages += 1
                returned += len(batch)
                raw_assignments += len(batch)
                for item in batch:
                    review = parse_review(item, language, args.app_id, collected_at)
                    existing = reviews.get(review["reviewId"])
                    if existing:
                        if language not in existing["languageStreams"]:
                            existing["languageStreams"].append(language)
                    else:
                        reviews[review["reviewId"]] = review
                if not next_token:
                    stream_stats[language] = {"pages": pages, "returned": returned, "terminated": True}
                    break
                if next_token in seen_tokens:
                    raise RuntimeError(f"repeated continuation token for {language}")
                seen_tokens.add(next_token)
                token = next_token
                if args.delay:
                    time.sleep(args.delay)
    except Exception as exc:
        manifest["failures"].append({"language": language, "error": type(exc).__name__})
        write_json(args.manifest_output, manifest)
        raise

    rows = sorted(reviews.values(), key=lambda row: (row["reviewedAt"] or "", row["reviewId"]), reverse=True)
    manifest.update(
        {
            "rawReviewAssignments": raw_assignments,
            "uniqueReviewCount": len(rows),
            "duplicateAssignments": raw_assignments - len(rows),
            "jsonlOutput": str(args.jsonl_output),
            "csvOutput": str(args.csv_output),
        }
    )
    write_review_files(args.jsonl_output, args.csv_output, rows)
    write_json(args.manifest_output, manifest)
    print(json.dumps({"uniqueReviewCount": len(rows), "rawReviewAssignments": raw_assignments}, ensure_ascii=False))


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("review timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def segment_summary(rows: list[dict]) -> dict[str, float | int]:
    count = len(rows)
    low = sum(row["score"] <= 2 for row in rows)
    positive = sum(row["score"] >= 4 for row in rows)
    return {
        "review_count": count,
        "mean_rating": round(sum(row["score"] for row in rows) / count, 4) if count else 0,
        "low_review_count": low,
        "low_review_share": round(low * 100 / count, 4) if count else 0,
        "positive_review_count": positive,
        "positive_review_share": round(positive * 100 / count, 4) if count else 0,
    }


def aggregate(rows: list[dict], source_sha256: str, as_of: date, min_segment_size: int) -> list[dict]:
    if len(rows) != len({row.get("reviewId") for row in rows}):
        raise ValueError("reviewId values must be unique")
    for row in rows:
        if row.get("score") not in range(1, 6) or not isinstance(row.get("thumbsUpCount", 0), int) or row.get("thumbsUpCount", 0) < 0:
            raise ValueError("invalid rating or thumbs-up count")
        parse_iso(row["reviewedAt"])

    result: list[dict] = []

    def add(section: str, segment: str, metric: str, value: object, unit: str, denominator: object = "", start: str = "", end: str = "", note: str = "") -> None:
        result.append(dict(zip(AGGREGATE_FIELDS, (section, segment, metric, value, unit, denominator, start, end, note, source_sha256))))

    timestamps = [parse_iso(row["reviewedAt"]) for row in rows]
    add("scope", "snapshot", "review_count", len(rows), "count")
    add("scope", "snapshot", "substantive_text_count", sum(bool((row.get("content") or "").strip()) for row in rows), "count", len(rows))
    add("scope", "snapshot", "reviewed_at_start", min(timestamps).isoformat(), "timestamp")
    add("scope", "snapshot", "reviewed_at_end", max(timestamps).isoformat(), "timestamp")
    add("scope", "snapshot", "nonempty_language_stream_count", len({language for row in rows for language in row.get("languageStreams", [])}), "count")
    assignments = sum(len(row.get("languageStreams", [])) for row in rows)
    add("scope", "snapshot", "language_stream_assignments", assignments, "count")
    add("scope", "snapshot", "duplicate_stream_assignments", assignments - len(rows), "count")
    replies = sum(bool(row.get("hasDeveloperReply") or row.get("replyContent")) for row in rows)
    add("engagement", "all", "developer_reply_count", replies, "count", len(rows))
    add("engagement", "all", "developer_reply_share", round(replies * 100 / len(rows), 4), "percent", len(rows))
    thumbs = [row.get("thumbsUpCount", 0) for row in rows]
    add("engagement", "all", "thumbs_up_total", sum(thumbs), "count")
    add("engagement", "all", "reviews_with_thumbs_up", sum(value > 0 for value in thumbs), "count", len(rows))

    overall = segment_summary(rows)
    for metric, value in overall.items():
        add("overall", "all", metric, value, "percent" if metric.endswith("share") else "stars" if metric == "mean_rating" else "count", len(rows) if metric.endswith("share") else "")

    ratings = Counter(row["score"] for row in rows)
    for score in range(1, 6):
        add("rating", str(score), "review_count", ratings[score], "count", len(rows))
        add("rating", str(score), "review_share", round(ratings[score] * 100 / len(rows), 4), "percent", len(rows))

    as_of_utc = datetime.combine(as_of, datetime_time.min, timezone.utc)
    periods = {
        "recent_90_days": (as_of_utc - timedelta(days=90), as_of_utc),
        "previous_90_days": (as_of_utc - timedelta(days=180), as_of_utc - timedelta(days=90)),
    }
    for name, (start, end) in periods.items():
        subset = [row for row in rows if start <= parse_iso(row["reviewedAt"]) < end]
        for metric, value in segment_summary(subset).items():
            add("period", name, metric, value, "percent" if metric.endswith("share") else "stars" if metric == "mean_rating" else "count", len(subset) if metric.endswith("share") else "", start.isoformat(), end.isoformat())

    by_language: dict[str, list[dict]] = {}
    for row in rows:
        for language in row.get("languageStreams", []):
            if not isinstance(language, str) or not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z]{2})?", language):
                raise ValueError("invalid language stream")
            by_language.setdefault(language, []).append(row)
    suppressed = [language for language, subset in by_language.items() if len(subset) < min_segment_size]
    for language, subset in sorted(by_language.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(subset) < min_segment_size:
            continue
        for metric, value in segment_summary(subset).items():
            add("language_stream", language, metric, value, "percent" if metric.endswith("share") else "stars" if metric == "mean_rating" else "count", len(subset) if metric.endswith("share") else "", note="queried locale; not detected review language")
    add("language_stream", "suppressed", "stream_count", len(suppressed), "count", note=f"streams with fewer than {min_segment_size} reviews")

    low_english = [row for row in rows if row["score"] <= 2 and "en" in row.get("languageStreams", [])]
    add("low_review_theme", "english_stream", "denominator", len(low_english), "count", note="1-2 stars; multi-label keyword matching")
    for name, pattern in THEMES.items():
        matched = sum(bool(pattern.search(row.get("content") or "")) for row in low_english)
        add("low_review_theme", name, "matched_count", matched, "count", len(low_english), note="English stream; multi-label keyword matching")
        add("low_review_theme", name, "matched_share", round(matched * 100 / len(low_english), 4) if low_english else 0, "percent", len(low_english), note="English stream; multi-label keyword matching")
    return result


def summarize(args: argparse.Namespace) -> None:
    raw = args.input.read_bytes()
    rows = [json.loads(line) for line in raw.decode().splitlines() if line]
    output = aggregate(rows, hashlib.sha256(raw).hexdigest(), date.fromisoformat(args.as_of), args.min_segment_size)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=AGGREGATE_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output)
    temporary.replace(args.output)
    print(json.dumps({"aggregateRows": len(output), "sourceReviews": len(rows)}, ensure_ascii=False))


def self_test(_: argparse.Namespace) -> None:
    raw_review = [
        "review-id", ["ignored user", [None, 2, None, [None, None, "ignored image"]]], 1, None,
        "slow login", [1_700_000_000, 0], 2, ["developer", "ignored reply", [1_700_000_100, 0]],
        None, [], "1.0", None, None, None, None, None, 1,
    ]
    parsed = parse_review(raw_review, "en", "example.app", "2026-08-11T00:00:00+00:00")
    assert "userName" not in parsed and "replyContent" not in parsed and parsed["score"] == 1
    assert spreadsheet_safe("=formula") == "'=formula"
    rows = [parsed, {**parsed, "reviewId": "review-id-2", "content": "works", "score": 5}]
    result = aggregate(rows, "0" * 64, date(2026, 8, 11), 1)
    assert any(row["section"] == "low_review_theme" and row["segment"] == "reliability_performance" and row["metric"] == "matched_count" and row["value"] == 1 for row in result)
    assert not ({"reviewId", "userName", "userImage", "content", "replyContent"} & set(AGGREGATE_FIELDS))
    with TemporaryDirectory() as directory:
        write_review_files(Path(directory) / "reviews.jsonl", Path(directory) / "reviews.csv", rows)
        with (Path(directory) / "reviews.csv").open(encoding="utf-8-sig") as file:
            assert next(csv.reader(file)) == ["리뷰내용", "별점"]
    print("self-test: ok")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    crawl_parser = commands.add_parser("crawl", help="crawl public review streams into ignored local data files")
    crawl_parser.add_argument("--app-id", default="com.salesforce.chatter")
    crawl_parser.add_argument("--languages", nargs="+", default=list(LANGUAGE_STREAMS))
    crawl_parser.add_argument("--page-size", type=int, default=4500)
    crawl_parser.add_argument("--delay", type=float, default=0.25)
    crawl_parser.add_argument("--timeout", type=int, default=30)
    crawl_parser.add_argument("--retries", type=int, default=3)
    crawl_parser.add_argument("--jsonl-output", type=Path, default=Path("data/raw/salesforce_chatter_google_play_reviews.jsonl"))
    crawl_parser.add_argument("--csv-output", type=Path, default=Path("data/processed/salesforce_reviews_content_rating.csv"))
    crawl_parser.add_argument("--manifest-output", type=Path, default=Path("data/processed/salesforce_reviews_manifest.json"))
    crawl_parser.set_defaults(run=crawl)

    summary_parser = commands.add_parser("summarize", help="write a privacy-safe aggregate CSV")
    summary_parser.add_argument("input", type=Path)
    summary_parser.add_argument("--output", type=Path, required=True)
    summary_parser.add_argument("--as-of", default=datetime.now(timezone.utc).date().isoformat())
    summary_parser.add_argument("--min-segment-size", type=int, default=10)
    summary_parser.set_defaults(run=summarize)

    test_parser = commands.add_parser("self-test", help="run deterministic parser and aggregation checks")
    test_parser.set_defaults(run=self_test)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.run(arguments)
