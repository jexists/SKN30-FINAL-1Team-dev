"""동결 범위별 작성·전체 검토 1회·부분 수정 1회를 외부 통신 없이 검사한다."""

import asyncio
import copy
import json
import re
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
    """Drive adapter tests through the one request-wide workflow boundary."""
    seen = []
    replies = iter(responses)

    def respond(call):
        seen.append(copy.deepcopy(call))
        response = next(replies)
        if isinstance(response, BaseException):
            raise response
        return response

    def call_for(spec, schema, stage, payload, *, role=None):
        return {
            "instructions": spec.instructions,
            "input_text": json.dumps(payload, ensure_ascii=False, default=str),
            "schema": schema,
            "stage": stage,
            "role": role or spec.writer_role,
            "skill_role": spec.writer_role,
        }

    def output_error(error):
        if isinstance(error, ValidationError):
            return LLMError("llm_output_schema_mismatch")
        if isinstance(error, (LLMError, ValueError, PermissionError)):
            return error
        if isinstance(error, TimeoutError):
            return LLMError("report_generation_timeout")
        return LLMError("report_generation_failed")

    async def workflow(spec):
        sections = copy.deepcopy(spec.prefilled_sections)
        task_count = review_count = repair_count = 0
        degraded = False
        for unit in spec.units:
            payload = (
                {
                    "scope": unit.scope,
                    "source": spec.source[unit.scope],
                    "previous_draft": None,
                    "issues": [],
                }
                if spec.report_kind == "meeting"
                else spec.source
            )
            task_count += 1
            try:
                response = respond(call_for(spec, unit.schema, f"{spec.stage}.generate", payload))
                section = unit.schema.model_validate(response)
                spec.validate_unit(unit, section, None, unit.locations)
            except BaseException as error:
                if isinstance(error, asyncio.CancelledError):
                    raise
                raise output_error(error) from None
            sections[unit.scope] = section

        draft_v1 = spec.assemble(sections)
        spec.validate_draft(draft_v1)
        spec.on_draft(1, draft_v1)
        review_count = 1
        task_count += 1
        review_payload = {"source": spec.source, "draft": draft_v1.model_dump(mode="json")}
        try:
            response = respond(
                call_for(
                    spec,
                    harness.ReportReview,
                    f"{spec.stage}.review",
                    review_payload,
                    role=harness.REVIEWER_ROLE,
                )
            )
            if not isinstance(response, dict) or not isinstance(response.get("issues"), list):
                raise LLMError("llm_output_schema_mismatch")
            raw_issues = response["issues"]
            if any(not isinstance(issue, (str, dict)) or not issue for issue in raw_issues):
                raise LLMError("llm_output_schema_mismatch")
        except BaseException as error:
            if isinstance(error, asyncio.CancelledError):
                raise
            normalized = output_error(error)
            harness.retain_valid_draft(normalized, stage=f"{spec.stage}.review")
            return harness.WorkflowResult(draft_v1, 1, True, task_count, review_count, 0)

        location_to_unit = {location: unit for unit in spec.units for location in unit.locations}
        repairs = []
        for raw in raw_issues:
            if isinstance(raw, dict):
                location = raw.get("location")
            elif spec.report_kind != "meeting":
                location = "fields[0].value"
            else:
                match = re.match(
                    r"^`?((?:deal_reports\[\d+\]|common_report|unassigned_report)\.[a-z_]+)",
                    raw.strip(),
                )
                location = match[1] if match else None
            unit = location_to_unit.get(location)
            if unit is None:
                degraded = True
                harness.log_agent_event(
                    f"{spec.stage}.review",
                    outcome="degraded",
                    reason_code="review_scope_unknown",
                )
                continue
            current = next((item for item in repairs if item[0] is unit), None)
            if current is None:
                repairs.append((unit, {location}, [raw]))
            else:
                current[1].add(location)
                current[2].append(raw)

        draft = draft_v1
        revised = False
        for unit, locations, issues in repairs:
            previous = sections[unit.scope]
            payload = (
                {
                    "scope": unit.scope,
                    "source": spec.source[unit.scope],
                    "previous_draft": previous.model_dump(mode="json"),
                    "issues": issues,
                }
                if spec.report_kind == "meeting"
                else {
                    "source": spec.source,
                    "draft": draft_v1.model_dump(mode="json"),
                    "issues": issues,
                }
            )
            task_count += 1
            repair_count += 1
            try:
                response = respond(call_for(spec, unit.schema, f"{spec.stage}.revise", payload))
                replacement = unit.schema.model_validate(response)
                spec.validate_unit(unit, replacement, previous, frozenset(locations))
                candidate_sections = {**sections, unit.scope: replacement}
                candidate = spec.assemble(candidate_sections)
                try:
                    spec.validate_draft(candidate)
                except (TypeError, ValueError, ValidationError) as error:
                    raise LLMError("report_output_invalid") from error
            except BaseException as error:
                if isinstance(error, asyncio.CancelledError):
                    raise
                normalized = output_error(error)
                harness.retain_valid_draft(normalized, stage=f"{spec.stage}.revise")
                degraded = True
                continue
            sections = candidate_sections
            draft = candidate
            revised = True

        if revised:
            spec.on_draft(2, draft)
        return harness.WorkflowResult(
            draft, 2 if revised else 1, degraded, task_count, review_count, repair_count
        )

    monkeypatch.setattr(harness, "run_report_workflow", workflow)
    return seen


def effective_instructions(call):
    """단계 계약과 실제 role에 제공되는 스킬 내용을 함께 검사한다."""
    return (
        call["instructions"]
        + "\n"
        + "\n".join(file["content"] for file in harness.skill_files(call["skill_role"]).values())
    )


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
    assert [item["role"] for item in seen] == [
        writer.WRITER_ROLE,
        writer.WRITER_ROLE,
        writer.WRITER_ROLE,
        harness.REVIEWER_ROLE,
    ]
    assert len(result.deal_reports) == 2
    assert result.deal_reports[1].body == contract.NO_DEAL_EVIDENCE_TEXT
    contract.validate_reports(source, result)
    assert all(
        "/skills/report-style/SKILL.md" in harness.skill_files(call["skill_role"]) for call in seen
    )
    assert all("# 영업보고서 공통 작성 기준" not in call["instructions"] for call in seen)


def test_meeting_heading_guidance_reaches_each_stage_and_repairs_scope(monkeypatch):
    responses = [
        {
            "title": "보안 승인 후 예산 검토",
            "body": "**논의 내용**\n\nA는 보안 승인을 받은 뒤 예산을 검토할 예정입니다.",
        },
        {"body": "**미팅 목적**\n\n구매팀과 미팅을 진행했습니다."},
        {
            "body": "- 추가 자료 요청은 대상 딜 확인이 필요합니다.\n"
            "- 기타 메모는 의미를 특정하기 어려워 추가 확인이 필요합니다.",
        },
        {"issues": ["unassigned_report.body: 귀속 불명확한 내용을 항목별 bullet로 유지하라."]},
        {"body": "- 추가 자료 요청은 대상 딜 확인이 필요합니다."},
    ]
    seen = scripted(monkeypatch, responses)

    result = asyncio.run(writer.run(sample()))

    heading_rule = "필요한 항목은 Markdown **굵은 소제목**을 독립된 한 줄에 쓰고"
    assert all(heading_rule in effective_instructions(call) for call in seen)
    bullet_rule = (
        "`unassigned_report`는 실제 딜 귀속이 불명확해 확인이 필요한 내용만 항목별 Markdown `- "
        "내용` 목록"
    )
    assert all(bullet_rule in effective_instructions(call) for call in seen)
    assert seen[3]["role"] == harness.REVIEWER_ROLE
    assert json.loads(seen[-1]["input_text"])["scope"] == "unassigned_report"
    assert result.unassigned_report.body.startswith("- ")
    assert "**고객 요구**" not in result.unassigned_report.body
    assert result.deal_reports[1].title == contract.NO_DEAL_EVIDENCE_TEXT
    assert result.deal_reports[1].body == contract.NO_DEAL_EVIDENCE_TEXT


def test_meeting_action_tail_keeps_bullets_and_narrative_rules_through_repair(monkeypatch):
    action_body = (
        "**논의 내용**\n\n보안 승인 후 예산 검토 예정이라고 밝혔습니다.\n\n"
        "**후속 조치**\n\n"
        "- 요청 | 보안 체크리스트 전달 | 담당: 본인 | 기한: 내일(기준일 미확인) | "
        "완료 기준: 전달 확인 | 조건: 보안 승인 후"
    )
    responses = [
        {"title": "보안 승인 후 예산 검토", "body": action_body},
        {"body": "**미팅 목적**\n\n구매팀과 미팅을 진행했습니다."},
        {"body": "**합의사항**\n\n도입 합의 여부는 미확인입니다."},
        {"issues": ["deal_reports[0].body: 후속 조치의 조건을 보존하라."]},
        {"title": "보안 승인 후 예산 검토", "body": action_body},
    ]
    seen = scripted(monkeypatch, responses)

    result = asyncio.run(writer.run(sample()))

    assert len(seen) == 5
    for call in seen:
        instructions = effective_instructions(call)
        assert (
            "마지막 후속 조치는 소제목 뒤 빈 줄에 핵심어 중심의 Markdown 순서 없는 목록"
            in instructions
        )
        assert "한 항목당 조치 1건" in instructions
        assert "소제목 뒤 빈 줄에 합니다체 서술 문단" in instructions
        assert "- 후속 조치 미확인" in instructions
        assert contract.NO_DEAL_EVIDENCE_TEXT in instructions
    assert result.deal_reports[0].body == action_body
    assert result.deal_reports[0].body.split("**후속 조치**\n\n", 1)[1].startswith("- ")
    assert "담당: 본인" in result.deal_reports[0].body
    assert "기한: 내일(기준일 미확인)" in result.deal_reports[0].body
    assert "조건: 보안 승인 후" in result.deal_reports[0].body


def test_one_review_repairs_only_identified_scope_then_returns(monkeypatch):
    repaired = {
        "title": "보안 승인 후 예산 검토",
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
    assert repair_input["previous_draft"] == {"kind": "deal", **initial_responses()[0]}
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
    assert events[-1]["call_count"] == len(seen)
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
                {
                    "title": "보안 승인 후 예산 검토",
                    "body": "보안 승인 후 예산 검토 예정입니다.",
                },
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
    assert len(seen) == len(responses)


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
    assert len(seen) == len(responses) + 1


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
