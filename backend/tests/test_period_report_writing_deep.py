"""기간 보고서 Deep Agent의 실제 SDK 경로를 합성 모델로 검사한다. DB/API는 호출하지 않는다."""

import asyncio
import copy
import json
from uuid import UUID

import pytest
from langchain_core.messages import AIMessage
from test_report_writing_deep import ScriptedModel, call

from app.agents import period_report_writing_deep as period
from app.agents import report_writing_deep as writer
from app.services.llm import LLMError

MEETING_A = UUID(int=101)
MEETING_B = UUID(int=102)


def sample():
    reports = [
        {
            "id": str(UUID(int=200 + index)),
            "sales_deal_id": str(UUID(int=300 + index)),
            "source_activity_id": str(meeting_id),
            "report_date": "2026-08-31",
            "title": title,
            "values": {"body": body},
        }
        for index, (meeting_id, title, body) in enumerate(
            [
                (MEETING_A, "합성회사 A · 보안 제품", "보안 승인 후 예산을 검토할 예정이다."),
                (MEETING_A, "합성회사 A · 운영 제품", "가격 비교 자료를 요청했다."),
                (MEETING_B, "합성회사 B · 분석 제품", "기술팀 검토 중이며 도입은 미확정이다."),
            ],
            1,
        )
    ]
    return {
        "report_kind": "daily",
        "report_date": "2026-08-31",
        "template_snapshot": {
            "id": "builtin-daily-freeform",
            "name": "일일보고서",
            "fields": [
                {
                    "id": "body",
                    "label": "보고서 본문",
                    "type": "textarea",
                    "required": True,
                    "aiFilled": True,
                }
            ],
        },
        "content": {
            "values": {"body": "사용자가 작성하던 메모"},
            "activities": [
                {
                    "id": row["id"],
                    "refId": row["id"],
                    "source": "업무보고서",
                    "included": True,
                    "title": row["title"],
                    "desc": row["values"]["body"],
                }
                for row in reports
            ],
            "attachments": [],
        },
        "transcript": "추가 메모: 자료 요청을 구매 확정으로 쓰지 말 것.",
        "guidance": "조건과 미확정 사항을 보존해주세요.",
        "report_sources": {
            "reports": reports,
            "meetings": [
                {
                    "activity_id": str(MEETING_A),
                    "common_report": {"body": "합성회사 A의 구매팀과 미팅했다."},
                    "unassigned_report": {
                        "body": "딜 미지정 · 확인 필요: ‘그것도 보내주세요.’의 대상은 불명확하다."
                    },
                },
                {
                    "activity_id": str(MEETING_B),
                    "common_report": {"body": "합성회사 B의 기술팀과 온라인으로 만났다."},
                    "unassigned_report": None,
                },
            ],
        },
    }


def test_normalized_direct_activities_override_legacy_content_metadata():
    source = sample()
    source["content"]["activities"].append(
        {
            "source": "캘린더",
            "included": True,
            "title": "클라이언트가 보낸 오래된 활동",
        }
    )
    source["report_sources"]["activities"] = [
        {
            "id": str(UUID(int=700)),
            "source": "캘린더",
            "included": True,
            "title": "DB에서 조회한 확정 활동",
        }
    ]

    normalized = period._source(source)

    assert normalized["activities"] == source["report_sources"]["activities"]
    assert "오래된 활동" not in str(normalized["activities"])


def draft():
    return {
        "fields": [
            {
                "field_id": "body",
                "value": "합성회사 A의 구매팀과 미팅했다. 보안 제품은 보안 승인 후 예산을 "
                "검토할 예정이며, 운영 제품은 가격 비교 자료를 요청했다. ‘그것도 보내주세요.’는 "
                "대상 딜이 불명확하여 확인이 필요하다.\n\n"
                "합성회사 B의 기술팀과 온라인으로 만났다. 분석 제품은 기술팀 검토 중이며 "
                "도입은 아직 확정되지 않았다.",
            }
        ],
        "summary": "두 회사 미팅의 조건부 검토와 자료 요청을 정리했다.",
    }


def period_sample(kind):
    source = sample()
    monthly = kind == "monthly"
    source.update(
        report_kind=kind,
        report_date="2026-09-30" if monthly else "2026-09-06",
        period_start="2026-09-01" if monthly else "2026-08-31",
        period_end="2026-09-30" if monthly else "2026-09-06",
        transcript=None,
    )
    source["template_snapshot"].update(
        id=f"builtin-{kind}-freeform", name="월간보고서" if monthly else "주간보고서"
    )
    source["content"]["activities"] = []
    values = (
        [
            (
                "2026-09-06",
                "2026-08-31",
                "2026-09-06",
                "주간 문의가 세 건 있었으나 각 문의의 날짜는 기록되지 않았다.",
            ),
            (
                "2026-09-13",
                "2026-09-07",
                "2026-09-13",
                "9월 9일 보안 심의는 아직 승인되지 않았고 예산도 확보되지 않았다.",
            ),
        ]
        if monthly
        else [
            ("2026-09-01", None, None, "비교 자료를 요청했으며 구매 합의는 없었다."),
            ("2026-09-04", None, None, "보안 승인 후 예산을 검토하기로 했다."),
        ]
    )
    source["report_sources"] = {
        "reports": [
            {
                "id": str(UUID(int=400 + index)),
                "submission_id": str(UUID(int=500 + index)),
                "report_kind": "weekly" if monthly else "daily",
                "sales_deal_id": None,
                "source_activity_id": None,
                "report_date": report_date,
                "period_start": start,
                "period_end": end,
                "title": f"합성 {'주간' if monthly else '일일'} 보고서 {index}",
                "values": {"body": body},
            }
            for index, (report_date, start, end, body) in enumerate(values, 1)
        ],
        "meetings": [],
    }
    return source


def manifest(source):
    normalized = period._source(source)
    return period._evidence_catalog(normalized)[0]


def evidence_keys(source):
    return [item["source_key"] for item in manifest(source)]


def read_all(source):
    return call("read_period_evidence", source_keys=evidence_keys(source))


def batch_review(*, issues=None, supports=None):
    return call(
        "PeriodBatchReview",
        issues=issues or [],
        supports=supports or [],
    )


def support(draft_quote, source_key, evidence_quote, *, unit_id="field:0"):
    return {
        "unit_id": unit_id,
        "draft_quote": draft_quote,
        "source_key": source_key,
        "evidence_quote": evidence_quote,
    }


def oversized_meeting_source():
    source = sample()
    reports = []
    for index in range(3):
        report = copy.deepcopy(source["report_sources"]["reports"][0])
        report.update(
            id=str(UUID(int=1_200 + index)),
            sales_deal_id=str(UUID(int=1_300 + index)),
            source_activity_id=str(MEETING_A),
            values={"body": chr(ord("가") + index) * 50_000},
        )
        reports.append(report)
    source["report_sources"] = {
        "reports": reports,
        "meetings": source["report_sources"]["meetings"][:1],
    }
    return source


def test_initial_input_inlines_run_context_and_manifest_but_not_activity_or_attachment_body():
    source = sample()
    activity_note = "직접 활동의 상세 근거는 reader에서만 보인다."
    attachment_extract = "첨부 추출문도 reader에서만 보인다."
    source["report_sources"] = {
        "reports": [],
        "meetings": [],
        "activities": [
            {
                "id": str(UUID(int=701)),
                "source": "캘린더",
                "title": "확정 활동",
                "note": activity_note,
            }
        ],
    }
    source["content"]["attachments"] = [
        {
            "id": str(UUID(int=801)),
            "name": "evidence.txt",
            "state": "done",
            "extract": attachment_extract,
        }
    ]
    good = {
        "fields": [{"field_id": "body", "value": f"{activity_note} {attachment_extract}"}],
        "summary": "직접 활동과 첨부 근거를 확인했다.",
    }
    model = ScriptedModel(
        responses=[
            read_all(source),
            call("review_period_report", draft=good),
            call("ReportReview", issues=[]),
        ]
    )

    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == good

    initial = json.loads(model._seen[0][-1].content)
    assert initial["run_context"]["template_snapshot"] == source["template_snapshot"]
    assert initial["run_context"]["current_values"] == source["content"]["values"]
    assert initial["run_context"]["transcript"] == source["transcript"]
    assert initial["run_context"]["guidance"] == source["guidance"]
    assert [item["source_type"] for item in initial["source_manifest"]] == [
        "direct_activity",
        "attachment",
    ]
    assert activity_note not in model._seen[0][-1].content
    assert attachment_extract not in model._seen[0][-1].content

    read = json.loads(model._seen[1][-1].content)["sources"]
    assert activity_note in str(read)
    assert attachment_extract in str(read)
    reviewed = json.loads(model._seen[2][-1].content)["source"]
    assert set(reviewed) == {"run_context", "review_batch", "evidence"}
    assert reviewed["review_batch"] == {
        "batch_index": 1,
        "batch_count": 1,
        "source_keys": evidence_keys(source),
    }
    assert reviewed["evidence"] == read


def test_review_requires_every_manifest_source_to_have_been_read():
    source = sample()
    model = ScriptedModel(
        responses=[
            call("review_period_report", draft=draft()),
            read_all(source),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )

    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == draft()
    coverage = json.loads(model._seen[1][-1].content)
    assert coverage["review_kind"] == "coverage"
    assert coverage["issues"][0]["code"] == "period_report_source_coverage_missing"
    assert coverage["issues"][0]["missing_source_keys"] == evidence_keys(source)
    assert coverage["remaining_reviews"] == writer.MAX_REVIEWS - 1


def test_evidence_request_key_count_duplicates_and_key_chars_are_bounded():
    source = sample()
    valid = evidence_keys(source)
    model = ScriptedModel(
        responses=[
            call("read_period_evidence", source_keys=[]),
            call(
                "read_period_evidence",
                source_keys=[valid[0]] * (period.MAX_EVIDENCE_KEYS_PER_CALL + 1),
            ),
            call(
                "read_period_evidence",
                source_keys=["x" * (period.MAX_EVIDENCE_KEY_CHARS_PER_CALL + 1)],
            ),
            read_all(source),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )

    asyncio.run(period.run(source, model=model))

    for turn in (1, 2, 3):
        result = json.loads(model._seen[turn][-1].content)
        assert result == {"error": "period_report_evidence_request_invalid"}


def test_evidence_reader_requires_explicit_keys_and_never_falls_back_to_full_dump():
    source = sample()
    model = ScriptedModel(
        responses=[
            call("read_period_evidence"),
            read_all(source),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )

    asyncio.run(period.run(source, model=model))

    tool_error = model._seen[1][-1].content
    assert "source_keys" in tool_error
    assert "합성회사" not in tool_error
    assert "보안 승인 후 예산" not in tool_error


def test_evidence_response_chars_are_bounded_and_successful_batches_cover_sources(monkeypatch):
    source = sample()
    source["report_sources"] = {"reports": [], "meetings": []}
    source["content"]["activities"] = []
    source["content"]["attachments"] = [
        {
            "id": str(UUID(int=810 + index)),
            "name": f"evidence-{index}.txt",
            "state": "done",
            "extract": marker * 200,
        }
        for index, marker in enumerate(("첫 첨부 근거", "둘째 첨부 근거"), 1)
    ]
    normalized = period._source(source)
    _, catalog = period._evidence_catalog(normalized)
    keys = list(catalog)
    single_limit = max(period._single_evidence_chars(catalog[key]) for key in keys)
    assert period._json_chars({"sources": list(catalog.values())}) > single_limit
    monkeypatch.setattr(period, "MAX_EVIDENCE_RESPONSE_CHARS", single_limit)
    good = {
        "fields": [{"field_id": "body", "value": "첫 첨부 근거와 둘째 첨부 근거"}],
        "summary": "",
    }
    model = ScriptedModel(
        responses=[
            call("read_period_evidence", source_keys=keys),
            call("read_period_evidence", source_keys=[keys[0]]),
            call("read_period_evidence", source_keys=[keys[1]]),
            call("review_period_report", draft=good),
            batch_review(supports=[support("첫 첨부 근거", keys[0], "첫 첨부 근거")]),
            batch_review(supports=[support("둘째 첨부 근거", keys[1], "둘째 첨부 근거")]),
            call("ReportReview", issues=[]),
        ]
    )

    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == good

    too_large = json.loads(model._seen[1][-1].content)
    assert too_large["error"] == "period_report_evidence_too_large"
    assert too_large["response_chars"] > too_large["max_chars"]


def test_oversized_logical_source_is_deterministically_chunked_and_can_complete():
    source = oversized_meeting_source()
    normalized = period._source(source)
    first_manifest, first_catalog = period._evidence_catalog(normalized)
    second_manifest, second_catalog = period._evidence_catalog(normalized)

    assert first_manifest == second_manifest
    assert first_catalog == second_catalog
    assert len(first_manifest) >= 2
    parent_key = f"meeting:{MEETING_A}"
    assert [item["chunk_index"] for item in first_manifest] == list(
        range(1, len(first_manifest) + 1)
    )
    assert {item["chunk_count"] for item in first_manifest} == {len(first_manifest)}
    assert {item["parent_source_key"] for item in first_manifest} == {parent_key}
    assert {item["source_group_key"] for item in first_manifest} == {parent_key}
    assert all(
        period._single_evidence_chars(first_catalog[item["source_key"]])
        <= period.MAX_EVIDENCE_RESPONSE_CHARS
        for item in first_manifest
    )
    chunks = [first_catalog[item["source_key"]] for item in first_manifest]
    expected = json.dumps(
        {
            "source_key": parent_key,
            "source_type": "meeting_bundle",
            "meeting_bundle": {
                "deal_reports": source["report_sources"]["reports"],
                "meetings": source["report_sources"]["meetings"],
            },
        },
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    assert chunks[0]["fragment_start"] == 0
    assert chunks[0]["fragment_overlap_chars"] == 0
    for previous, current in zip(chunks, chunks[1:], strict=False):
        overlap = current["fragment_overlap_chars"]
        assert 0 < overlap <= period.EVIDENCE_CHUNK_OVERLAP_CHARS
        assert previous["fragment_end"] - current["fragment_start"] == overlap
        assert previous["content_fragment"][-overlap:] == current["content_fragment"][:overlap]
    assert chunks[-1]["fragment_end"] == len(expected)
    reconstructed = chunks[0]["content_fragment"] + "".join(
        chunk["content_fragment"][chunk["fragment_overlap_chars"] :] for chunk in chunks[1:]
    )
    assert reconstructed == expected

    keys = [item["source_key"] for item in first_manifest]
    good = {
        "fields": [{"field_id": "body", "value": "가" * 10}],
        "summary": "",
    }
    model = ScriptedModel(
        responses=[
            *[call("read_period_evidence", source_keys=[key]) for key in keys],
            call("review_period_report", draft=good),
            *[
                batch_review(
                    supports=(
                        [support("가" * 10, key, "가" * 10)]
                        if "가" * 10 in first_catalog[key]["content_fragment"]
                        else []
                    )
                )
                for key in keys
            ],
            call("ReportReview", issues=[]),
        ]
    )

    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == good


def test_chunk_search_never_serializes_a_fragment_larger_than_the_response_limit(monkeypatch):
    observed = []
    original = period._single_evidence_chars

    def record(item):
        observed.append(len(item.get("content_fragment", "")))
        return original(item)

    monkeypatch.setattr(period, "_single_evidence_chars", record)
    period._chunk_frozen_source(
        "attachment:large",
        {
            "source_type": "attachment",
            "content": "가" * (period.MAX_EVIDENCE_RESPONSE_CHARS * 4),
        },
    )

    assert observed
    assert max(observed) <= period.MAX_EVIDENCE_RESPONSE_CHARS


def test_small_source_catalog_shape_is_unchanged():
    source = sample()
    source_manifest, catalog = period._evidence_catalog(period._source(source))

    assert all(
        set(item)
        == {
            "source_key",
            "source_type",
            "source_activity_id",
            "report_date",
            "deal_count",
            "content_chars",
        }
        for item in source_manifest
    )
    assert all(
        set(catalog[item["source_key"]]) == {"source_key", "source_type", "meeting_bundle"}
        for item in source_manifest
    )


def test_semantic_reviewer_batches_evidence_and_caps_combined_issues():
    source = sample()
    source["report_sources"] = {"reports": [], "meetings": []}
    source["content"]["activities"] = []
    source["content"]["attachments"] = [
        {
            "id": str(UUID(int=1_400 + index)),
            "name": f"large-{index}.txt",
            "state": "done",
            "extract": marker * 70_000,
        }
        for index, marker in enumerate(("가", "나"), 1)
    ]
    keys = evidence_keys(source)
    first_issues = [f"batch-1-{index}" for index in range(20)]
    second_issues = [f"batch-2-{index}" for index in range(20)]
    good = {
        "fields": [{"field_id": "body", "value": "가가가가가 및 나나나나나 근거"}],
        "summary": "",
    }
    model = ScriptedModel(
        responses=[
            call("read_period_evidence", source_keys=[keys[0]]),
            call("read_period_evidence", source_keys=[keys[1]]),
            call("review_period_report", draft=good),
            batch_review(issues=first_issues),
            batch_review(issues=second_issues),
            call("review_period_report", draft=good),
            batch_review(supports=[support("가가가가가", keys[0], "가가가가가")]),
            batch_review(supports=[support("나나나나나", keys[1], "나나나나나")]),
            call("ReportReview", issues=[]),
        ]
    )

    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == good

    reviewer_payloads = []
    for messages in model._seen:
        for message in messages:
            if message.type != "human":
                continue
            try:
                payload = json.loads(message.content)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and "review_batch" in payload.get("source", {}):
                reviewer_payloads.append(payload)
    assert len(reviewer_payloads) == 4
    assert [payload["source"]["review_batch"]["batch_index"] for payload in reviewer_payloads] == [
        1,
        2,
        1,
        2,
    ]
    assert all(
        period._json_chars({"evidence": payload["source"]["evidence"]})
        <= period.MAX_EVIDENCE_RESPONSE_CHARS
        for payload in reviewer_payloads
    )
    root_after_review = model._seen[5]
    feedback = next(
        json.loads(message.content)
        for message in root_after_review
        if message.type == "tool" and message.name == "review_period_report"
    )
    assert feedback["issues"] == [*first_issues, *second_issues[:10]]


def test_multi_batch_global_support_review_rejects_unsupported_conclusion():
    source = sample()
    source["report_sources"] = {"reports": [], "meetings": []}
    source["content"]["activities"] = []
    source["content"]["attachments"] = [
        {
            "id": str(UUID(int=1_500)),
            "name": "customer-a.txt",
            "state": "done",
            "extract": "고객 A는 보안 검토 중이다. " * 4_000,
        },
        {
            "id": str(UUID(int=1_501)),
            "name": "customer-b.txt",
            "state": "done",
            "extract": "고객 B는 예산 승인 대기 중이다. " * 4_000,
        },
    ]
    keys = evidence_keys(source)
    assert (
        len(
            period._review_evidence_batches(
                keys, period._evidence_catalog(period._source(source))[1]
            )
        )
        == 2
    )
    bad = {
        "fields": [
            {
                "field_id": "body",
                "value": "고객 A는 보안 검토 중이다. 고객 B는 예산 승인 대기 중이다. "
                "두 고객 모두 계약을 최종 확정했다.",
            }
        ],
        "summary": "",
    }
    good = {
        "fields": [
            {
                "field_id": "body",
                "value": "고객 A는 보안 검토 중이며 고객 B는 예산 승인 대기 중이다.",
            }
        ],
        "summary": "",
    }
    bad_supports = [
        [support("고객 A는 보안 검토 중이다.", keys[0], "고객 A는 보안 검토 중이다.")],
        [
            support(
                "고객 B는 예산 승인 대기 중이다.",
                keys[1],
                "고객 B는 예산 승인 대기 중이다.",
            )
        ],
    ]
    good_supports = [
        [support("고객 A는 보안 검토 중이며", keys[0], "고객 A는 보안 검토 중이다.")],
        [
            support(
                "고객 B는 예산 승인 대기 중이다.",
                keys[1],
                "고객 B는 예산 승인 대기 중이다.",
            )
        ],
    ]
    unsupported = "fields[0].value의 계약 최종 확정은 어느 지원 기록에도 없다. 제거하라."
    model = ScriptedModel(
        responses=[
            call("read_period_evidence", source_keys=[keys[0]]),
            call("read_period_evidence", source_keys=[keys[1]]),
            call("review_period_report", draft=bad),
            batch_review(supports=bad_supports[0]),
            batch_review(supports=bad_supports[1]),
            call("ReportReview", issues=[unsupported]),
            call("review_period_report", draft=good),
            batch_review(supports=good_supports[0]),
            batch_review(supports=good_supports[1]),
            call("ReportReview", issues=[]),
        ]
    )

    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == good
    assert unsupported in str(model._seen[6])
    first_global_review = json.loads(model._seen[5][-1].content)
    assert "두 고객 모두 계약을 최종 확정했다" in str(first_global_review)
    assert "계약을 최종 확정" not in str(
        first_global_review["review_units"][0]["validated_supports"]
    )


def test_multi_batch_deduplicates_equivalent_supports_and_reviews_empty_support_units():
    source = sample()
    facts = [f"공통 일정 {index:03d}은 추후 안내한다." for index in range(100)]
    report_text = " ".join(facts)
    source["template_snapshot"]["fields"] = [{"id": "body"}, {"id": "note"}]
    source["transcript"] = report_text + " " * 300
    source["report_sources"] = {"reports": [], "meetings": []}
    source["content"]["activities"] = []
    source["content"]["attachments"] = [
        {
            "id": str(UUID(int=1_600 + index)),
            "name": f"large-{index}.txt",
            "state": "done",
            "extract": report_text + " " * 300 + marker * 70_000,
        }
        for index, marker in enumerate(("가", "나"), 1)
    ]
    keys = evidence_keys(source)
    report = {
        "fields": [
            {"field_id": "body", "value": report_text},
            {"field_id": "note", "value": "선택 자료에는 계약 확정 정보가 없다."},
        ],
        "summary": "",
    }
    units = period._draft_review_units(period.ReportDraftOutput.model_validate(report))
    assert len(units) > 2
    assert all(len(unit["text"]) <= period.DRAFT_REVIEW_TARGET_CHARS for unit in units)
    unit_ids = {
        fact: next(unit["unit_id"] for unit in units if fact in unit["text"]) for fact in facts
    }
    model = ScriptedModel(
        responses=[
            call("read_period_evidence", source_keys=[keys[0]]),
            call("read_period_evidence", source_keys=[keys[1]]),
            call("review_period_report", draft=report),
            batch_review(
                supports=[
                    support(
                        fact,
                        period.INLINE_TRANSCRIPT_SOURCE_KEY,
                        fact,
                        unit_id=unit_ids[fact],
                    )
                    for fact in facts
                ]
            ),
            batch_review(
                supports=[support(fact, keys[1], fact, unit_id=unit_ids[fact]) for fact in facts]
            ),
            call("ReportReview", issues=[]),
        ]
    )

    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == report

    second_batch = json.loads(model._seen[4][-1].content)
    assert second_batch["source"]["run_context"]["transcript"] is None
    global_review = json.loads(model._seen[5][-1].content)
    review_units = global_review["review_units"]
    assert sum(len(unit["validated_supports"]) for unit in review_units) == len(facts)
    assert (
        next(
            unit for unit in review_units if "계약 확정 정보가 없다" in unit["draft_unit"]["text"]
        )["validated_supports"]
        == []
    )


def test_multi_batch_keeps_conflicting_contexts_for_the_global_reviewer():
    source = sample()
    source["report_sources"] = {"reports": [], "meetings": []}
    source["content"]["activities"] = []
    source["content"]["attachments"] = [
        {
            "id": str(UUID(int=1_700)),
            "name": "confirmed.txt",
            "state": "done",
            "extract": "계약 확정 완료. " * 8_000,
        },
        {
            "id": str(UUID(int=1_701)),
            "name": "not-confirmed.txt",
            "state": "done",
            "extract": "계약 확정이 아니다. " * 8_000,
        },
    ]
    keys = evidence_keys(source)
    bad = {"fields": [{"field_id": "body", "value": "계약 확정"}], "summary": ""}
    good = {
        "fields": [{"field_id": "body", "value": "자료 간 계약 확정 여부가 일치하지 않는다."}],
        "summary": "",
    }
    conflict = "fields[0].value: 계약 확정 여부가 출처 간 충돌한다. 충돌 상태를 명시하라."
    model = ScriptedModel(
        responses=[
            call("read_period_evidence", source_keys=[keys[0]]),
            call("read_period_evidence", source_keys=[keys[1]]),
            call("review_period_report", draft=bad),
            batch_review(supports=[support("계약 확정", keys[0], "계약 확정")]),
            batch_review(supports=[support("계약 확정", keys[1], "계약 확정")]),
            call("ReportReview", issues=[conflict]),
            call("review_period_report", draft=good),
            batch_review(supports=[support("계약 확정 여부", keys[0], "계약 확정")]),
            batch_review(supports=[support("계약 확정 여부", keys[1], "계약 확정")]),
            call("ReportReview", issues=[]),
        ]
    )

    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == good

    first_global_review = json.loads(model._seen[5][-1].content)
    contexts = str(first_global_review["review_units"][0]["validated_supports"])
    assert "계약 확정 완료" in contexts
    assert "계약 확정이 아니다" in contexts
    assert conflict in str(model._seen[6])


def test_batch_supports_require_real_draft_source_and_quotes():
    unit = {"unit_id": "field:0", "path": "fields[0].value", "text": "실제 초안 문구"}
    source = {"source_key": "attachment:1", "content": "실제 원문 문구"}
    review = period.PeriodBatchReview(
        issues=[],
        supports=[
            support("실제 초안 문구", "attachment:1", "실제 원문 문구"),
            support("없는 초안", "attachment:1", "실제 원문 문구"),
            support("실제 초안 문구", "attachment:missing", "실제 원문 문구"),
            support("실제 초안 문구", "attachment:1", "없는 원문"),
        ],
    )

    assert period._validated_batch_supports(
        review, batch=[source], units=[unit], transcript=None
    ) == [
        {
            **review.supports[0].model_dump(),
            "evidence_context": "실제 원문 문구",
        }
    ]


def test_batch_support_context_preserves_negation_around_a_quote():
    unit = {"unit_id": "field:0", "path": "fields[0].value", "text": "계약 확정"}
    source = {"source_key": "attachment:1", "content": "계약 확정이 아니다"}
    review = period.PeriodBatchReview(
        issues=[],
        supports=[support("계약 확정", "attachment:1", "계약 확정")],
    )

    validated = period._validated_batch_supports(
        review, batch=[source], units=[unit], transcript=None
    )

    assert validated[0]["evidence_context"] == "계약 확정이 아니다"


def test_review_units_do_not_cut_a_long_sentence_in_the_middle():
    sentence = "보안 검토가 끝나면 " + "세부 조건을 확인하고 " * 50 + "계약을 확정한다"

    assert len(sentence) > period.DRAFT_REVIEW_TARGET_CHARS
    assert period._review_text_parts(sentence) == [sentence]


def test_more_than_one_reader_batch_can_cover_all_direct_sources():
    source = sample()
    source["content"]["activities"] = []
    source["report_sources"] = {
        "reports": [],
        "meetings": [],
        "activities": [
            {
                "id": str(UUID(int=900 + index)),
                "source": "캘린더",
                "title": f"직접 활동 {index}",
            }
            for index in range(period.MAX_EVIDENCE_KEYS_PER_CALL + 1)
        ],
    }
    keys = evidence_keys(source)
    model = ScriptedModel(
        responses=[
            call(
                "read_period_evidence",
                source_keys=keys[: period.MAX_EVIDENCE_KEYS_PER_CALL],
            ),
            call(
                "read_period_evidence",
                source_keys=keys[period.MAX_EVIDENCE_KEYS_PER_CALL :],
            ),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )

    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == draft()


def test_actual_graph_reads_sources_revises_and_returns_accepted_draft_unchanged():
    source = sample()
    original = copy.deepcopy(source)
    good = draft()
    bad = draft()
    bad["fields"][0]["value"] = "합성회사 A의 예산이 승인되었다."
    model = ScriptedModel(
        responses=[
            read_all(source),
            call("review_period_report", draft=bad),
            call(
                "ReportReview",
                issues=["예산 승인은 원문에 없다. 보안 승인 후 검토 예정으로 고쳐라."],
            ),
            call("review_period_report", draft=good),
            call("ReportReview", issues=[]),
            call("ReportDraftOutput", **bad),
        ]
    )

    result = asyncio.run(period.run(source, model=model))

    assert result.model_dump(mode="json") == good
    assert source == original
    assert len(model._seen) == 5  # 승인 후 작성자의 추가 호출/변형 없이 종료한다.
    assert "예산 승인은 원문에 없다" in str(model._seen[3])
    assert "줄글" in str(model._seen[0][0].content)
    assert "딜 미지정" in str(model._seen[2])
    assert "합성회사 B" in str(model._seen[2])
    assert all(not {"execute", "web_search"} & tools for tools in model._tool_sets)
    assert all("read_report_sources" not in tools for tools in model._tool_sets)


def test_subagent_reads_only_target_meeting_with_common_and_unassigned(monkeypatch):
    import deepagents.middleware.subagents

    specs = []
    original = deepagents.middleware.subagents.create_sub_agent

    def record_subagent(spec, **kwargs):
        specs.append(spec)
        return original(spec, **kwargs)

    monkeypatch.setattr(deepagents.middleware.subagents, "create_sub_agent", record_subagent)
    source = sample()
    meeting_a_key = f"meeting:{MEETING_A}"
    meeting_b_key = f"meeting:{MEETING_B}"
    model = ScriptedModel(
        responses=[
            call(
                "task",
                subagent_type="general-purpose",
                description=f'source_keys=["{meeting_a_key}"] 합성회사 A 미팅 초안을 정리하라.',
            ),
            call("read_period_evidence", source_keys=[meeting_a_key]),
            AIMessage(content="A의 두 딜과 공통·미지정 내용을 함께 정리한다."),
            call("read_period_evidence", source_keys=[meeting_b_key]),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )

    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == draft()
    initial = json.loads(model._seen[0][-1].content)
    scoped = json.loads(model._seen[2][-1].content)["sources"][0]
    assert initial["run_context"]["current_values"] == source["content"]["values"]
    assert initial["run_context"]["transcript"] == source["transcript"]
    assert {item["source_key"] for item in initial["source_manifest"]} == {
        meeting_a_key,
        meeting_b_key,
    }
    assert scoped["meeting_bundle"]["deal_reports"] == source["report_sources"]["reports"][:2]
    assert scoped["meeting_bundle"]["meetings"] == source["report_sources"]["meetings"][:1]
    assert "그것도 보내주세요" in str(scoped)
    assert "합성회사 B" not in str(scoped)
    delegated = next(message.content for message in model._seen[1] if message.type == "human")
    assert f'source_keys=["{meeting_a_key}"]' in delegated
    assert "보안 권한 경계가 아니" in model._seen[1][0].content
    assert specs
    for spec in specs:
        assert {
            tool.name if hasattr(tool, "name") else tool.__name__ for tool in spec["tools"]
        } == {"read_period_evidence"}
        assert not any("finish_accepted" in item.name for item in spec.get("middleware", []))


def test_unknown_meeting_cannot_read_other_meeting_sources():
    source = sample()
    model = ScriptedModel(
        responses=[
            call("read_period_evidence", source_keys=[f"meeting:{UUID(int=999)}"]),
            read_all(source),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )
    asyncio.run(period.run(source, model=model))
    result = json.loads(model._seen[1][-1].content)
    assert result.get("error")
    assert "합성회사" not in str(result)


@pytest.mark.parametrize("invalid", ["duplicate", "missing", "unexpected", "blank_body"])
def test_structural_field_errors_are_repaired_before_semantic_review(invalid):
    source = sample()
    bad = draft()
    if invalid == "duplicate":
        bad["fields"].append(copy.deepcopy(bad["fields"][0]))
    elif invalid == "missing":
        bad["fields"] = []
    elif invalid == "unexpected":
        bad["fields"][0]["field_id"] = "unrequested"
    else:
        bad["fields"][0]["value"] = " \n "
    model = ScriptedModel(
        responses=[
            read_all(source),
            call("review_period_report", draft=bad),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )

    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == draft()
    assert len(model._seen) == 4  # 잘못된 필드는 의미 검토 모델에 보내지 않는다.
    feedback = json.loads(model._seen[2][-1].content)
    assert feedback["review_kind"] == "structural"
    assert feedback["issues"]


def test_saved_multifield_template_remains_compatible():
    source = sample()
    source["template_snapshot"]["fields"] = [
        {"id": "summary", "label": "요약", "type": "textarea"},
        {"id": "next_plan", "label": "후속 계획", "type": "textarea"},
    ]
    source["content"]["values"] = {"summary": "", "next_plan": ""}
    good = {
        "fields": [
            {"field_id": "next_plan", "value": ""},
            {"field_id": "summary", "value": draft()["fields"][0]["value"]},
        ],
        "summary": "근거 없는 후속 기한은 채우지 않았다.",
    }
    model = ScriptedModel(
        responses=[
            read_all(source),
            call("review_period_report", draft=good),
            call("ReportReview", issues=[]),
        ]
    )
    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == good


@pytest.mark.parametrize("include_sources", [True, False])
def test_transcript_only_daily_is_allowed_without_linked_reports(include_sources):
    source = sample()
    source["content"]["activities"] = []
    source["content"]["values"] = {"body": ""}
    source["transcript"] = "전화 문의에 아직 답변이 없어 회신을 기다리고 있다."
    if include_sources:
        source["report_sources"] = {"reports": [], "meetings": []}
    else:
        source.pop("report_sources")
    good = {
        "fields": [{"field_id": "body", "value": source["transcript"]}],
        "summary": "전화 문의 회신 대기",
    }
    model = ScriptedModel(
        responses=[
            call("review_period_report", draft=good),
            call("ReportReview", issues=[]),
        ]
    )
    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == good
    assert source["transcript"] in str(model._seen[-1])


def test_direct_final_output_cannot_skip_semantic_review():
    source = sample()
    model = ScriptedModel(
        responses=[
            call("ReportDraftOutput", **draft()),
            read_all(source),
            call("ReportDraftOutput", **draft()),
            call("ReportReview", issues=["검토 예정이라는 조건을 분명히 보존하라."]),
            call("ReportDraftOutput", **draft()),
            call("ReportReview", issues=[]),
        ]
    )
    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == draft()
    assert len(model._seen) == 6
    assert "period_report_source_coverage_missing" in str(model._seen[1])
    assert "검토 예정이라는 조건" in str(model._seen[4])


def test_direct_final_submission_repairs_structure_and_passes_semantic_review():
    source = sample()
    bad = draft()
    bad["fields"][0]["field_id"] = "other"
    model = ScriptedModel(
        responses=[
            read_all(source),
            call("ReportDraftOutput", **bad),
            call("ReportDraftOutput", **draft()),
            call("ReportReview", issues=[]),
        ]
    )
    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == draft()
    assert len(model._seen) == 4
    assert "expected_ids" in str(model._seen[2])


def test_coverage_rejections_consume_review_limit_and_log_the_reason(monkeypatch, caplog):
    monkeypatch.setattr(writer, "MAX_REVIEWS", 2)
    model = ScriptedModel(
        responses=[
            call("review_period_report", draft=draft()),
            call("review_period_report", draft=draft()),
            call("review_period_report", draft=draft()),
        ]
    )

    with pytest.raises(LLMError, match="^period_report_agent_review_limit$"):
        asyncio.run(period.run(sample(), model=model))

    progress = [record.message for record in caplog.records if "agent_progress" in record.message]
    coverage = [
        message for message in progress if "period_report_source_coverage_missing" in message
    ]
    assert len(model._seen) == 3
    assert len(coverage) == 2
    assert '"review_attempt": 1' in coverage[0]
    assert '"review_attempt": 2' in coverage[1]
    assert any(
        '"reason_code": "period_report_agent_review_limit"' in message
        and '"review_attempt": 3' in message
        for message in progress
    )
    assert any(
        '"stage": "period_report_writing.summary"' in message
        and '"review_attempt": 2' in message
        and '"semantic_review_count": 0' in message
        for message in progress
    )


def test_review_limit_does_not_keep_retrying(monkeypatch):
    monkeypatch.setattr(writer, "MAX_REVIEWS", 2)
    model = ScriptedModel(
        responses=[
            read_all(sample()),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=["원문의 조건을 보존하라."]),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=["원문의 조건을 보존하라."]),
            call("review_period_report", draft=draft()),
        ]
    )
    with pytest.raises(LLMError, match="^period_report_agent_review_limit$"):
        asyncio.run(period.run(sample(), model=model))
    assert len(model._seen) == 6


def test_model_budget_includes_subagent_and_reviewer(monkeypatch):
    monkeypatch.setattr(writer, "MAX_MODEL_CALLS", 3)
    model = ScriptedModel(
        responses=[
            call("task", subagent_type="general-purpose", description="미팅별 초안"),
            AIMessage(content="미팅별 초안을 정리했다."),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )
    with pytest.raises(LLMError, match="^report_agent_model_call_limit$"):
        asyncio.run(period.run(sample(), model=model))
    assert len(model._seen) == 3


def test_run_timeout_is_bounded(monkeypatch):
    class SlowModel(ScriptedModel):
        async def _agenerate(self, messages, **kwargs):
            await asyncio.sleep(1)
            return self._generate(messages, **kwargs)

    monkeypatch.setattr(writer, "RUN_TIMEOUT_SECONDS", 0.01)
    model = SlowModel(responses=[AIMessage(content="wait")])
    with pytest.raises(LLMError, match="^period_report_agent_timeout$"):
        asyncio.run(period.run(sample(), model=model))


@pytest.mark.parametrize("kind", ["meeting", "quarterly", ""])
def test_unsupported_report_kind_is_rejected_before_model_call(kind):
    source = sample()
    source["report_kind"] = kind
    model = ScriptedModel(responses=[call("ReportDraftOutput", **draft())])
    with pytest.raises(LLMError, match="^period_report_kind_invalid$"):
        asyncio.run(period.run(source, model=model))
    assert model._seen == []


@pytest.mark.parametrize("invalid", [None, [], "", 0, False])
def test_falsy_non_mapping_report_sources_are_rejected(invalid):
    source = sample()
    source["report_sources"] = invalid
    model = ScriptedModel(responses=[call("ReportDraftOutput", **draft())])

    with pytest.raises(LLMError, match="^period_report_sources_invalid$"):
        asyncio.run(period.run(source, model=model))
    assert model._seen == []


@pytest.mark.parametrize("kind", ["weekly", "monthly"])
def test_period_sources_and_boundary_uncertainty_reach_reviewer_unchanged(kind):
    source = period_sample(kind)
    original = copy.deepcopy(source)
    good = {
        "fields": [
            {
                "field_id": "body",
                "value": (
                    "8월 31일~9월 6일 주간보고서에는 문의 세 건이 기록돼 있으나 "
                    "문의별 날짜가 없어 9월 실적으로 구분할 수 없다. "
                    "9월 9일 보안 심의는 미승인이며 예산도 미확보 상태였다."
                    if kind == "monthly"
                    else "비교 자료 요청이 있었지만 구매 합의는 없었다. "
                    "보안 승인을 받은 후 예산을 검토하기로 했다."
                ),
            }
        ],
        "summary": "제공된 하위 보고서의 조건과 불확실성을 보존했다.",
    }
    bad = copy.deepcopy(good)
    bad["fields"][0]["value"] = "9월 계약 세 건과 예산 승인이 확정됐다."
    model = ScriptedModel(
        responses=[
            read_all(source),
            call("review_period_report", draft=bad),
            call("ReportReview", issues=["문의와 검토를 계약·예산 확정으로 바꾸지 마라."]),
            call("review_period_report", draft=good),
            call("ReportReview", issues=[]),
            call("ReportDraftOutput", **bad),
        ]
    )

    result = asyncio.run(period.run(source, model=model))

    assert result.model_dump(mode="json") == good
    assert source == original
    assert len(model._seen) == 5
    shared = json.loads(model._seen[1][-1].content)["sources"]
    reviewed = json.loads(model._seen[2][-1].content)["source"]
    assert reviewed["run_context"]["report_kind"] == kind
    assert reviewed["run_context"]["period_start"] == source["period_start"]
    assert reviewed["run_context"]["period_end"] == source["period_end"]
    assert reviewed["evidence"] == shared
    assert "report_sources" not in reviewed
    if kind == "monthly":
        boundary = reviewed["evidence"][0]["child_submission"]["reports"][0]
        assert boundary["period_start"] < reviewed["run_context"]["period_start"]
        assert "각 문의의 날짜는 기록되지 않았다" in boundary["values"]["body"]
        assert "미승인" in result.fields[0].value


@pytest.mark.parametrize("kind", ["daily", "weekly", "monthly"])
def test_read_one_manifest_source_keeps_its_period_unit_and_boundaries(kind):
    source = sample() if kind == "daily" else period_sample(kind)
    keys = evidence_keys(source)
    good = draft()
    responses = [call("read_period_evidence", source_keys=[keys[0]])]
    if len(keys) > 1:
        responses.append(call("read_period_evidence", source_keys=keys[1:]))
    responses.extend([call("review_period_report", draft=good), call("ReportReview", issues=[])])
    model = ScriptedModel(responses=responses)

    asyncio.run(period.run(source, model=model))

    scoped = json.loads(model._seen[1][-1].content)["sources"][0]
    if kind == "daily":
        assert scoped["source_type"] == "meeting_bundle"
        assert scoped["meeting_bundle"]["deal_reports"] == source["report_sources"]["reports"][:2]
        assert scoped["meeting_bundle"]["meetings"] == source["report_sources"]["meetings"][:1]
    else:
        assert scoped["source_type"] == "child_submission"
        assert scoped["child_submission"]["reports"] == [source["report_sources"]["reports"][0]]


@pytest.mark.parametrize("kind", ["daily", "weekly", "monthly"])
def test_unselected_source_key_uses_one_error_without_exposing_evidence(kind):
    source = sample() if kind == "daily" else period_sample(kind)
    selected = evidence_keys(source)[0]
    model = ScriptedModel(
        responses=[
            call(
                "read_period_evidence",
                source_keys=[selected, "submission:not-selected"],
            ),
            read_all(source),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )
    asyncio.run(period.run(source, model=model))
    result = json.loads(model._seen[1][-1].content)
    assert result.get("error")
    assert "sources" not in result
    assert "합성" not in str(result)
    assert result["error"] == "period_report_source_not_selected"


@pytest.mark.parametrize("kind", ["weekly", "monthly"])
@pytest.mark.parametrize("missing", ["period_start", "period_end"])
def test_parent_period_is_required_before_model_call(kind, missing):
    source = period_sample(kind)
    source.pop(missing)
    model = ScriptedModel(responses=[call("ReportDraftOutput", **draft())])
    with pytest.raises(LLMError, match="^period_report_period_invalid$"):
        asyncio.run(period.run(source, model=model))
    assert model._seen == []
