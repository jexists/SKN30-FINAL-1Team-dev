"""동결 범위별 작성·전체 검토 1회·부분 수정 1회를 외부 통신 없이 검사한다."""

import asyncio
import copy
import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.agents.reports import harness
from app.agents.reports import meeting as writer
from app.agents.reports import meeting_contract as contract
from app.agents.reports.meeting_tools import create_meeting_tools
from app.schemas.meeting_content import (
    MeetingContentAnalysisOutput,
    MeetingContentInput,
    build_evidence_ledger,
)
from app.services.llm import LLMError, LLMNotConfigured

DEAL_A = UUID(int=1)
DEAL_B = UUID(int=2)


def scripted(monkeypatch, responses):
    seen = []
    replies = iter(responses)

    async def generate(**kwargs):
        seen.append(copy.deepcopy(kwargs))
        response = next(replies)
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr(harness, "generate_structured", generate)
    return seen


def sample():
    texts = [
        "구매팀과 만났다.",
        "A는 보안 승인 후 예산 검토 예정이다.",
        "그거 다시 보내달래.",
        "기타 메모 ???",
    ]
    transcript = "\n".join(texts)
    start = 0
    segments = []
    for index, text in enumerate(texts, 1):
        segments.append(
            {"segment_id": f"S{index:04}", "start": start, "end": start + len(text), "text": text}
        )
        start += len(text) + 1
    source = MeetingContentInput(
        transcript=transcript,
        selected_deal_ids=[DEAL_A, DEAL_B],
        segments=segments,
    )
    analysis = MeetingContentAnalysisOutput(
        assignments=[
            {"segment_id": "S0001", "applicability": {"scope": "meeting_context"}},
            {"segment_id": "S0002", "applicability": {"scope": "deal", "deal_ids": [DEAL_A]}},
            {"segment_id": "S0003", "applicability": {"scope": "unresolved"}},
            {"segment_id": "S0004", "applicability": {"scope": "out_of_scope"}},
        ]
    )
    return contract.ReportWritingInput(
        transcript=transcript,
        evidence=build_evidence_ledger(source, analysis),
        crm_context={"company": {"name": "합성회사"}},
    )


def draft():
    return {
        "deal_reports": [
            {
                "sales_deal_id": str(DEAL_A),
                "title": "보안 승인 후 예산 검토",
                "body": "A는 보안 승인을 받은 뒤 예산을 검토할 예정입니다.",
                "evidence_ids": ["S0002"],
            },
            {
                "sales_deal_id": str(DEAL_B),
                "title": contract.NO_DEAL_EVIDENCE_TEXT,
                "body": contract.NO_DEAL_EVIDENCE_TEXT,
                "evidence_ids": [],
            },
        ],
        "common_report": {"body": "구매팀과 미팅을 진행했습니다.", "evidence_ids": ["S0001"]},
        "unassigned_report": {
            "body": "추가 자료 요청은 대상 딜 확인이 필요합니다. 기타 메모는 의미를 "
            "특정하기 어려워 추가 확인이 필요합니다.",
            "evidence_ids": ["S0003", "S0004"],
        },
    }


def initial_responses():
    value = draft()
    return [
        {key: value["deal_reports"][0][key] for key in ("title", "body")},
        {"body": value["common_report"]["body"]},
        {"body": value["unassigned_report"]["body"]},
    ]


def test_valid_draft_is_reviewed_once_without_revision_and_ids_are_assigned(monkeypatch):
    source = sample()
    original = source.model_dump(mode="json")
    seen = scripted(monkeypatch, [*initial_responses(), {"issues": []}])
    result = asyncio.run(writer.run(source))
    assert result.model_dump(mode="json") == draft()
    assert source.model_dump(mode="json") == original
    assert len(seen) == 4
    assert seen[-1]["schema"] is harness.ReportReview
    assert all(item["report_mode"] is True for item in seen)
    assert len(result.deal_reports) == 2
    assert result.deal_reports[1].body == contract.NO_DEAL_EVIDENCE_TEXT
    contract.validate_reports(source, result)
    common = writer.COMMON_SKILL.read_text(encoding="utf-8")
    rules = (writer.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert all(common in call["instructions"] and rules in call["instructions"] for call in seen)


def test_one_review_repairs_only_identified_scope_then_returns(monkeypatch):
    repaired = {
        "title": "조건 확인",
        "body": "보안 승인 후 예산 검토 예정이며 기한은 미확인입니다.",
    }
    seen = scripted(
        monkeypatch,
        [
            *initial_responses(),
            {"issues": ["deal_reports[0].body: 기한 미확인을 보존하라."]},
            repaired,
        ],
    )
    result = asyncio.run(writer.run(sample()))
    assert len(seen) == 5
    assert sum(call["schema"] is harness.ReportReview for call in seen) == 1
    assert result.deal_reports[0].body == repaired["body"]
    assert result.common_report.model_dump() == draft()["common_report"]
    assert result.unassigned_report.model_dump() == draft()["unassigned_report"]
    repair_input = json.loads(seen[-1]["input_text"])
    assert repair_input["scope"] == "deal_reports[0]"
    assert repair_input["previous_draft"] == initial_responses()[0]
    assert repair_input["source"] == json.loads(seen[0]["input_text"])["source"]
    assert {item["segment"]["segment_id"] for item in repair_input["source"]["evidence"]} == {
        "S0001",
        "S0002",
    }


@pytest.mark.parametrize("stage", ["review", "repair"])
@pytest.mark.parametrize(
    "failure",
    [
        None,
        {},
        {"issues": [""]},
        RuntimeError("private-detail"),
        TimeoutError(),
        LLMError("llm_provider_error:429"),
        LLMError("llm_provider_error:503"),
        LLMError("llm_request_failed:ReadTimeout"),
        LLMError("llm_response_not_json"),
    ],
)
def test_malformed_or_failed_review_and_repair_preserve_valid_draft(
    monkeypatch, caplog, stage, failure
):
    events = []
    monkeypatch.setattr(writer, "log_agent_event", lambda *args, **kwargs: events.append(kwargs))
    responses = initial_responses()
    if stage == "repair":
        responses.append({"issues": ["deal_reports[0].body: 조건을 복원하라."]})
    seen = scripted(monkeypatch, [*responses, failure])
    result = asyncio.run(writer.run(sample()))
    assert result.model_dump(mode="json") == draft()
    assert len(seen) == (4 if stage == "review" else 5)
    assert events[-1]["model_call_count"] == len(seen)
    assert events[-1]["semantic_review_count"] == 1
    assert events[-1]["repair_count"] == int(stage == "repair")
    assert '"outcome": "degraded"' in caplog.text
    assert "valid_draft_fallback" in caplog.text
    assert "private-detail" not in caplog.text


@pytest.mark.parametrize("stage", ["initial", "repair"])
def test_output_contract_failure_preserves_only_an_existing_valid_draft(monkeypatch, stage):
    events = []
    monkeypatch.setattr(writer, "log_agent_event", lambda *args, **kwargs: events.append(kwargs))
    assemble = writer._assemble
    assemblies = 0

    def invalid_candidate(scopes, sections):
        nonlocal assemblies
        candidate = assemble(scopes, sections)
        assemblies += 1
        if assemblies == (1 if stage == "initial" else 2):
            candidate.deal_reports[0].evidence_ids.clear()
        return candidate

    monkeypatch.setattr(writer, "_assemble", invalid_candidate)
    responses = initial_responses()
    if stage == "repair":
        responses.extend(
            [
                {"issues": ["deal_reports[0].body: 조건을 복원하라."]},
                {"title": "조건 재확인", "body": "보안 승인 후 예산 검토 예정입니다."},
            ]
        )
    seen = scripted(monkeypatch, responses)
    if stage == "initial":
        with pytest.raises(ValueError, match="report_deal_evidence_mismatch"):
            asyncio.run(writer.run(sample()))
    else:
        result = asyncio.run(writer.run(sample()))
        assert result.model_dump(mode="json") == draft()
        contract.validate_reports(sample(), result)
    assert events[-1]["outcome"] == ("failed" if stage == "initial" else "degraded")
    assert events[-1]["model_call_count"] == len(seen) == len(responses)
    assert events[-1]["semantic_review_count"] == int(stage == "repair")
    assert events[-1]["repair_count"] == int(stage == "repair")


@pytest.mark.parametrize("stage", ["initial", "review", "repair"])
@pytest.mark.parametrize(
    "failure",
    [
        asyncio.CancelledError(),
        ValueError("input_invalid"),
        PermissionError("owner_invalid"),
        LLMError("report_input_invalid"),
        LLMNotConfigured("llm_not_configured"),
        LLMError("llm_provider_error:401"),
        LLMError("llm_provider_error:403"),
    ],
)
def test_cancellation_and_trust_errors_propagate(monkeypatch, stage, failure):
    events = []
    monkeypatch.setattr(writer, "log_agent_event", lambda *args, **kwargs: events.append(kwargs))
    responses = [] if stage == "initial" else initial_responses()
    if stage == "repair":
        responses.append({"issues": ["deal_reports[0].body: 조건을 복원하라."]})
    seen = scripted(monkeypatch, [*responses, failure])
    with pytest.raises(type(failure)) as caught:
        asyncio.run(writer.run(sample()))
    assert caught.value is failure
    assert events[-1]["outcome"] == "failed"
    assert events[-1]["model_call_count"] == len(seen) == len(responses) + 1
    assert events[-1]["semantic_review_count"] == int(stage != "initial")
    assert events[-1]["repair_count"] == int(stage == "repair")


@pytest.mark.parametrize("stage", ["initial", "review", "repair"])
def test_payload_serialization_failure_does_not_count_a_model_attempt(monkeypatch, stage):
    events = []
    monkeypatch.setattr(writer, "log_agent_event", lambda *args, **kwargs: events.append(kwargs))
    dumps = json.dumps

    def serialize(payload, **kwargs):
        if isinstance(payload, dict) and "source" in payload:
            current = (
                "review"
                if "scope" not in payload
                else ("repair" if payload["previous_draft"] is not None else "initial")
            )
            if current == stage:
                raise ValueError("Circular reference detected")
        return dumps(payload, **kwargs)

    monkeypatch.setattr(writer.json, "dumps", serialize)
    responses = [] if stage == "initial" else initial_responses()
    if stage == "repair":
        responses.append({"issues": ["deal_reports[0].body: 조건을 복원하라."]})
    seen = scripted(monkeypatch, responses)
    with pytest.raises(ValueError, match="Circular reference detected"):
        asyncio.run(writer.run(sample()))
    assert events[-1]["outcome"] == "failed"
    assert events[-1]["model_call_count"] == events[-1]["call_count"] == len(seen) == len(responses)
    assert (
        events[-1]["semantic_review_count"]
        == events[-1]["review_attempt"]
        == int(stage == "repair")
    )
    assert events[-1]["repair_count"] == 0


@pytest.mark.parametrize(
    "failure",
    [
        None,
        RuntimeError("private-detail"),
        {
            "title": contract.NO_DEAL_EVIDENCE_TEXT,
            "body": contract.NO_DEAL_EVIDENCE_TEXT,
        },
    ],
)
def test_first_generation_failure_cannot_become_no_discussion(monkeypatch, failure):
    seen = scripted(monkeypatch, [failure])
    with pytest.raises(LLMError):
        asyncio.run(writer.run(sample()))
    assert len(seen) == 1


def test_input_hash_revalidated_before_generation(monkeypatch):
    source = sample()
    source.evidence.transcript_sha256 = "0" * 64
    seen = scripted(monkeypatch, [])
    with pytest.raises(ValidationError, match="report_transcript_hash_mismatch"):
        asyncio.run(writer.run(source))
    assert seen == []


def test_scope_inputs_keep_other_deals_and_past_reports_out_of_current_evidence(monkeypatch):
    source = sample()
    source.attachments = [{"extract": "합성 배경자료"}]
    histories = [
        {"sales_deal_id": str(deal), "body": "과거 예산 승인"} for deal in (DEAL_A, DEAL_B)
    ]
    products = [
        {"sales_deal_id": str(deal), "kind": "product_details"} for deal in (DEAL_A, DEAL_B)
    ]
    source.crm_context.update(
        deals=[{"sales_deal_id": str(deal)} for deal in (DEAL_A, DEAL_B)],
        previous_reports=histories,
        additional_context=products,
    )
    seen = scripted(monkeypatch, [*initial_responses(), {"issues": []}])
    result = asyncio.run(writer.run(source))
    inputs = [json.loads(call["input_text"])["source"] for call in seen[:3]]
    assert inputs[0]["previous_reports"] == [histories[0]]
    assert "previous_reports" not in inputs[0]["crm_context"]
    assert inputs[0]["crm_context"]["deals"] == [{"sales_deal_id": str(DEAL_A)}]
    assert inputs[0]["crm_context"]["additional_context"] == [products[0]]
    assert inputs[0]["attachments"] == source.attachments
    assert {item["segment"]["segment_id"] for item in inputs[1]["evidence"]} == {"S0001"}
    assert {item["segment"]["segment_id"] for item in inputs[2]["evidence"]} == {"S0003", "S0004"}
    assert result.deal_reports[1].evidence_ids == []
    for read in create_meeting_tools(source):
        assert read(UUID(int=99)) == {"error": "deal_not_selected"}


def test_unidentified_feedback_does_not_rewrite_unrelated_scopes(monkeypatch, caplog):
    seen = scripted(monkeypatch, [*initial_responses(), {"issues": ["막연한 수정 요청"]}])
    assert asyncio.run(writer.run(sample())).model_dump(mode="json") == draft()
    assert len(seen) == 4
    assert "review_scope_unknown" in caplog.text


def test_no_selected_deals_generates_shared_sections_only(monkeypatch):
    source = sample().model_dump(mode="json")
    source["evidence"]["selected_deal_ids"] = []
    source["evidence"]["items"][1]["applicability"] = {"scope": "unresolved", "deal_ids": []}
    source = contract.ReportWritingInput.model_validate(source)
    seen = scripted(
        monkeypatch,
        [
            {"body": "구매팀과 미팅했습니다."},
            {"body": "예산 검토 예정이며 요청 대상은 미확인입니다."},
            {"issues": []},
        ],
    )
    result = asyncio.run(writer.run(source))
    assert result.deal_reports == []
    assert len(seen) == 3
    contract.validate_reports(source, result)


def test_review_evidence_mentions_do_not_select_unrelated_repair_scopes(monkeypatch):
    revised = {"body": "공통 미팅 맥락을 보존했습니다."}
    seen = scripted(
        monkeypatch,
        [
            *initial_responses(),
            {"issues": ["common_report.body: deal_reports[0].body의 내용을 공통과 구분하라."]},
            revised,
        ],
    )
    result = asyncio.run(writer.run(sample()))
    assert len(seen) == 5
    assert json.loads(seen[-1]["input_text"])["scope"] == "common_report"
    assert result.deal_reports[0].body == draft()["deal_reports"][0]["body"]
    assert result.common_report.body == revised["body"]


def test_one_failed_scope_repair_keeps_other_successful_repairs(monkeypatch):
    revised = {"body": "공통 목적과 활동 방식을 명확히 기록했습니다."}
    seen = scripted(
        monkeypatch,
        [
            *initial_responses(),
            {
                "issues": [
                    "common_report.body: 목적을 보존하라.",
                    "deal_reports[0].body: 조건을 보존하라.",
                ]
            },
            revised,
            None,
        ],
    )
    result = asyncio.run(writer.run(sample()))
    assert len(seen) == 6
    assert result.common_report.body == revised["body"]
    assert result.deal_reports[0].body == draft()["deal_reports"][0]["body"]
    contract.validate_reports(sample(), result)


def test_generated_identity_is_rejected_instead_of_overriding_server_scope(monkeypatch):
    forged = {**initial_responses()[0], "sales_deal_id": str(DEAL_B), "evidence_ids": ["S9999"]}
    scripted(monkeypatch, [forged])
    with pytest.raises(LLMError, match="llm_output_schema_mismatch"):
        asyncio.run(writer.run(sample()))
