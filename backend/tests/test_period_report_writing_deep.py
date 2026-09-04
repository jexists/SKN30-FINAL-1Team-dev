"""기간 보고서의 bounded source units와 Deep Agent 작성·검토 경로를 검사한다."""

import asyncio
import copy
import json
from uuid import UUID

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError
from test_report_writing_deep import ScriptedModel, call

from app.agents import period_report_writing_deep as period
from app.agents import report_deep_harness as harness
from app.agents import report_writing
from app.agents.report_writing import ReportDraftOutput
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
            "activities": [],
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


def draft():
    return {
        "fields": [
            {
                "field_id": "body",
                "value": "합성회사 A의 구매팀과 미팅했습니다. 보안 제품은 보안 승인 후 예산을 "
                "검토할 예정이며, 운영 제품은 가격 비교 자료를 요청했습니다. 추가 자료 요청은 "
                "대상 딜 확인이 필요합니다.\n\n"
                "합성회사 B의 기술팀과 온라인으로 만났습니다. 분석 제품은 기술팀 검토 중이며 "
                "도입은 아직 확정되지 않았습니다.",
            }
        ]
    }


def delegated_prefix(
    source_id: str | None = None,
    *,
    role: str = "daily-report-writer",
):
    read_args = {} if source_id is None else {"source_id": source_id}
    return [
        call(
            "task",
            subagent_type=harness.DELEGATED_WRITER_NAME,
            description=f"role={role}\n동결 자료를 읽고 기간 보고서 본문 초안을 작성해 주세요.",
        ),
        call("read_report_sources", **read_args),
        AIMessage(content="근거의 사실·조건·불확실성을 보존한 본문 초안입니다."),
    ]


def test_period_prompt_requires_an_internal_report_instead_of_a_schedule_summary():
    assert report_writing.PROMPT_VERSION == "report_writing.v17"
    assert "본문 초안 작성은 서버가 지정한 task 하위 작성자에게" in period.SYSTEM_PROMPT
    assert "직접 본문을 쓰지 마라" in period.SYSTEM_PROMPT
    assert "첫 검토의 의미 지적은 수정 조언" in period.SYSTEM_PROMPT
    assert "의미 검토를 반복하지 않는다" in period.SYSTEM_PROMPT
    assert period.PERIOD_WRITER_ROLES == {
        "daily": "daily-report-writer",
        "weekly": "weekly-report-writer",
        "monthly": "monthly-report-writer",
    }
    assert "날짜나 자료 존재만 요약했다면 핵심 누락" in period.REVIEW_PROMPT
    assert "단순 문체 취향이 아니라 수정 대상" in period.REVIEW_PROMPT
    assert (
        "guidance는 이번 보고서 작성자가 직접 제공한 최신 추가·정정 자료"
        in period.GUIDANCE_CONTRACT
    )
    assert (
        "딜·제품 귀속을 명시적으로 정정하면 그 발언에 한해 본문에 반영" in period.GUIDANCE_CONTRACT
    )
    assert "딜 미지정 상태 보존 규칙의 예외" in period.GUIDANCE_CONTRACT
    assert "정정하지 않은 불확실성은 그대로 유지" in period.GUIDANCE_CONTRACT
    skill = period._skill_text("daily")
    assert "# 기간 업무보고 공통 문체" in skill
    assert "# 일일업무보고 작성" in skill
    assert "문장 끝을 합니다체로 통일합니다" in skill
    assert "당일 실제 업무 결과와 고객 반응, 결정 조건" in skill
    assert "일정의 날짜·시간·장소만 다시 나열하지 말고" in skill
    assert "# 주간업무보고 작성" not in skill
    assert "# 월간업무보고 작성" not in skill


def period_sample(kind: str):
    source = sample()
    monthly = kind == "monthly"
    source.update(
        report_kind=kind,
        report_date="2026-09-30" if monthly else "2026-09-06",
        period_start="2026-09-01" if monthly else "2026-08-31",
        period_end="2026-09-30" if monthly else "2026-09-06",
        transcript=None,
    )
    source["report_sources"] = {
        "reports": [
            {
                "id": str(UUID(int=400 + index)),
                "submission_id": str(UUID(int=500 + index)),
                "report_kind": "weekly" if monthly else "daily",
                "report_date": report_date,
                "period_start": start,
                "period_end": end,
                "title": f"합성 보고서 {index}",
                "values": {"body": body},
            }
            for index, (report_date, start, end, body) in enumerate(
                [
                    ("2026-09-01", None, None, "비교 자료를 요청했으며 구매 합의는 없었다."),
                    ("2026-09-04", None, None, "보안 승인 후 예산을 검토하기로 했다."),
                ],
                1,
            )
        ],
        "meetings": [],
    }
    return source


def test_source_units_keep_each_meeting_boundary_and_shared_notes():
    units = period._source_units(period._source(sample()))

    assert [unit["source_type"] for unit in units] == ["meeting_bundle", "meeting_bundle"]
    first = units[0]["content"]
    assert len(first["deal_reports"]) == 2
    assert first["meeting_context"][0]["common_report"]["body"].startswith("합성회사 A")
    assert "딜 미지정" in first["meeting_context"][0]["unassigned_report"]["body"]


@pytest.mark.parametrize("kind", ["weekly", "monthly"])
def test_period_sources_are_grouped_by_child_submission(kind):
    units = period._source_units(period._source(period_sample(kind)))
    assert len(units) == 2
    assert all(unit["source_type"] == "child_submission" for unit in units)
    assert all(len(unit["content"]["reports"]) == 1 for unit in units)


def test_direct_activity_and_attachment_are_separate_units():
    source = sample()
    source["report_sources"] = {
        "reports": [],
        "meetings": [],
        "activities": [{"id": "activity-1", "source": "캘린더", "title": "확정 활동"}],
    }
    source["content"]["attachments"] = [
        {"id": "file-1", "name": "evidence.txt", "state": "done", "extract": "첨부 근거"}
    ]

    units = period._source_units(period._source(source))

    assert [unit["source_type"] for unit in units] == ["direct_activity", "attachment"]


def test_normalized_direct_activities_override_legacy_content_metadata():
    source = sample()
    source["content"]["activities"] = [
        {"source": "캘린더", "included": True, "title": "오래된 화면 값"}
    ]
    source["report_sources"]["activities"] = [
        {"id": "activity-1", "source": "캘린더", "title": "DB 확정 값"}
    ]
    assert period._source(source)["activities"] == source["report_sources"]["activities"]


def test_source_units_and_whole_prompt_have_hard_size_limits(monkeypatch):
    source = sample()
    source["report_sources"]["reports"][0]["values"]["body"] = "가" * 1_000
    monkeypatch.setattr(period, "MAX_SOURCE_UNIT_CHARS", 100)
    with pytest.raises(LLMError, match="period_report_source_unit_too_large"):
        period._source_units(period._source(source))

    monkeypatch.setattr(period, "MAX_SOURCE_UNIT_CHARS", 60_000)
    monkeypatch.setattr(period, "MAX_PERIOD_PROMPT_CHARS", 100)
    model = ScriptedModel(responses=[call("ReportDraftOutput", **draft())])
    with pytest.raises(LLMError, match="period_report_input_too_large"):
        asyncio.run(period.run(sample(), model=model))
    assert model._seen == []


def test_actual_deep_graph_delegates_reads_all_units_and_returns_reviewed_draft(caplog):
    source = sample()
    original = copy.deepcopy(source)
    model = ScriptedModel(
        responses=[
            *delegated_prefix(),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )

    result = asyncio.run(period.run(source, model=model))

    assert result.model_dump(mode="json") == draft()
    assert source == original
    assert len(model._seen) == 5
    supervisor_tools = next(tools for tools in model._tool_sets if "review_period_report" in tools)
    subagent_tools = next(tools for tools in model._tool_sets if "read_report_sources" in tools)
    assert {"task", "review_period_report", "ReportDraftOutput"} <= supervisor_tools
    assert "read_report_sources" not in supervisor_tools
    assert "read_report_sources" in subagent_tools
    assert "review_period_report" not in subagent_tools
    assert model._tool_sets[-1] == {"ReportReview"}
    payload = json.loads(model._seen[2][-1].content)
    assert len(payload["source_units"]) == 2
    assert "보안 승인 후 예산" in str(payload["source_units"])
    assert all(not {"execute", "web_search"} & tools for tools in model._tool_sets)
    assert "# 기간 업무보고 공통 문체" in model._seen[1][0].content
    assert "# 일일업무보고 작성" in model._seen[1][0].content
    assert period.GUIDANCE_CONTRACT in model._seen[1][0].content
    summary = next(
        json.loads(record.getMessage().removeprefix("agent_progress "))
        for record in caplog.records
        if '"stage": "period_report_writing.summary"' in record.getMessage()
    )
    assert summary["call_count"] == 5
    assert summary["delegation_count"] == 1
    assert summary["tool_call_count"] == 3


@pytest.mark.parametrize(
    ("kind", "role", "skill_heading"),
    [
        ("daily", "daily-report-writer", "# 일일업무보고 작성"),
        ("weekly", "weekly-report-writer", "# 주간업무보고 작성"),
        ("monthly", "monthly-report-writer", "# 월간업무보고 작성"),
    ],
)
def test_report_kind_deterministically_selects_its_writer_role(kind, role, skill_heading):
    source = sample() if kind == "daily" else period_sample(kind)
    model = ScriptedModel(
        responses=[
            *delegated_prefix(role=role),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )

    result = asyncio.run(period.run(source, model=model))

    assert result.model_dump(mode="json") == draft()
    request = json.loads(model._seen[0][-1].content)
    assert request["report_kind"] == kind
    assert request["writer_role"] == role
    assert role in model._seen[1][0].content
    assert skill_heading in model._seen[1][0].content


def test_subagent_reads_only_the_delegated_source_unit():
    source = sample()
    model = ScriptedModel(
        responses=[
            *delegated_prefix("meeting_bundle:1"),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )

    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == draft()

    scoped = json.loads(model._seen[2][-1].content)
    assert [unit["source_id"] for unit in scoped["source_units"]] == ["meeting_bundle:1"]
    assert "합성회사 A" in str(scoped)
    assert "합성회사 B" not in str(scoped)
    assert len(model._seen) == 5


def test_unselected_source_id_does_not_expose_frozen_sources():
    model = ScriptedModel(
        responses=[
            *delegated_prefix("meeting_bundle:999"),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )

    asyncio.run(period.run(sample(), model=model))

    denied = json.loads(model._seen[2][-1].content)
    assert denied == {"error": "period_report_source_not_selected"}
    assert "합성회사" not in str(denied)


def test_only_body_field_is_generated_and_structurally_checked():
    source = sample()
    bad = {
        "fields": [
            *draft()["fields"],
            {"field_id": "manager_note", "value": "AI가 덮어쓴 값"},
        ]
    }
    model = ScriptedModel(
        responses=[
            *delegated_prefix(),
            call("ReportDraftOutput", **bad),
            *delegated_prefix(),
            call("ReportDraftOutput", **draft()),
            call("ReportReview", issues=[]),
        ]
    )

    result = asyncio.run(period.run(source, model=model))

    assert result.model_dump(mode="json") == draft()
    feedback = json.loads(model._seen[4][-1].content.split("\n", 1)[1])
    assert feedback["issues"][0]["expected_ids"] == ["body"]
    assert feedback["issues"][0]["actual_ids"] == ["body", "manager_note"]


def test_semantic_issue_is_delegated_for_one_repair_then_returned(caplog):
    bad = copy.deepcopy(draft())
    bad["fields"][0]["value"] = "두 회사 모두 구매를 확정했다."
    model = ScriptedModel(
        responses=[
            *delegated_prefix(),
            call("ReportDraftOutput", **bad),
            call("ReportReview", issues=["확정 근거가 없으므로 조건과 미확정을 복원하라."]),
            *delegated_prefix(),
            call("ReportDraftOutput", **draft()),
        ]
    )

    result = asyncio.run(period.run(sample(), model=model))

    assert result.model_dump(mode="json") == draft()
    assert len(model._seen) == period.MAX_MODEL_CALLS
    assert json.loads(model._seen[5][-1].content.split("\n", 1)[1])["issues"] == [
        "확정 근거가 없으므로 조건과 미확정을 복원하라."
    ]
    summary = next(
        json.loads(record.getMessage().removeprefix("agent_progress "))
        for record in caplog.records
        if '"stage": "period_report_writing.summary"' in record.getMessage()
    )
    assert summary["delegation_count"] == 2
    assert summary["tool_call_count"] == 4
    assert summary["semantic_review_count"] == period.MAX_SEMANTIC_REVIEWS
    assert summary["outcome"] == "completed"
    review_events = [
        json.loads(record.getMessage().removeprefix("agent_progress "))
        for record in caplog.records
        if '"stage": "period_report_writing.review"' in record.getMessage()
    ]
    assert [event["reason_code"] for event in review_events] == [
        "review_feedback",
        "repair_contract_valid",
    ]
    assert all(event["outcome"] == "completed" for event in review_events)
    assert "확정 근거가 없으므로" not in caplog.text


def test_repair_is_returned_without_a_second_quality_review(caplog):
    first = copy.deepcopy(draft())
    first["fields"][0]["value"] = "두 회사 모두 구매를 확정했다."
    latest = copy.deepcopy(draft())
    latest["fields"][0]["value"] += " 담당자 확인도 이어가겠습니다."
    model = ScriptedModel(
        responses=[
            *delegated_prefix(),
            call("ReportDraftOutput", **first),
            call("ReportReview", issues=["확정 근거가 없어 조건을 복원해야 합니다."]),
            *delegated_prefix(),
            call("ReportDraftOutput", **latest),
        ]
    )

    result = asyncio.run(period.run(sample(), model=model))

    assert result.model_dump(mode="json") == latest
    assert len(model._seen) == period.MAX_MODEL_CALLS
    summary = next(
        json.loads(record.getMessage().removeprefix("agent_progress "))
        for record in caplog.records
        if '"stage": "period_report_writing.summary"' in record.getMessage()
    )
    assert summary["outcome"] == "completed"
    assert summary["review_attempt"] == period.MAX_REVIEWS
    assert summary["repair_count"] == period.MAX_REPAIRS
    assert summary["semantic_review_count"] == period.MAX_SEMANTIC_REVIEWS
    assert "completed_with_review_issues" not in summary
    assert "remaining_issue_count" not in summary
    assert sum(tools == {"ReportReview"} for tools in model._tool_sets) == 1


def test_structurally_invalid_repair_falls_back_to_previous_safe_draft(caplog):
    safe = copy.deepcopy(draft())
    safe["fields"][0]["value"] = "구매 확정 여부는 추가 확인이 필요합니다."
    invalid = {"fields": [{"field_id": "wrong", "value": "잘못된 필드"}]}
    model = ScriptedModel(
        responses=[
            *delegated_prefix(),
            call("ReportDraftOutput", **safe),
            call("ReportReview", issues=["고객별 조건이 누락되었습니다."]),
            *delegated_prefix(),
            call("ReportDraftOutput", **invalid),
        ]
    )

    result = asyncio.run(period.run(sample(), model=model))

    assert result.model_dump(mode="json") == safe
    assert len(model._seen) == period.MAX_MODEL_CALLS
    summary = next(
        json.loads(record.getMessage().removeprefix("agent_progress "))
        for record in caplog.records
        if '"stage": "period_report_writing.summary"' in record.getMessage()
    )
    assert summary["outcome"] == "completed"
    assert summary["semantic_review_count"] == period.MAX_SEMANTIC_REVIEWS


def test_repair_must_pass_final_ai_field_validation():
    bad = {"fields": [{"field_id": "wrong", "value": "잘못된 필드"}]}
    model = ScriptedModel(
        responses=[
            *delegated_prefix(),
            call("ReportDraftOutput", **bad),
            *delegated_prefix(),
            call("ReportDraftOutput", **bad),
        ]
    )
    with pytest.raises(LLMError, match="period_report_agent_structural_limit"):
        asyncio.run(period.run(sample(), model=model))


def test_direct_supervisor_draft_is_rejected_until_a_task_succeeds():
    model = ScriptedModel(
        responses=[
            call("ReportDraftOutput", **draft()),
            *delegated_prefix(),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )

    assert asyncio.run(period.run(sample(), model=model)).model_dump(mode="json") == draft()
    feedback = model._seen[1][-1].content
    assert "daily-report-writer task에 위임" in feedback
    assert len(model._seen) == 6


def test_empty_source_units_are_delegated_with_run_context():
    source = sample()
    source["report_sources"] = {"reports": [], "meetings": [], "activities": []}
    source["content"]["values"] = {"body": "고객 회신을 기다리고 있습니다."}
    source["transcript"] = "가격표를 전달했고 고객 회신을 기다리고 있습니다."
    model = ScriptedModel(
        responses=[
            *delegated_prefix(),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )

    asyncio.run(period.run(source, model=model))

    delegated_source = json.loads(model._seen[2][-1].content)
    assert delegated_source["source_units"] == []
    assert delegated_source["run_context"]["current_body"] == source["content"]["values"]["body"]
    assert delegated_source["run_context"]["transcript"] == source["transcript"]
    assert delegated_source["run_context"]["guidance"] == source["guidance"]


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update(report_kind="meeting"), "period_report_kind_invalid"),
        (
            lambda value: value["template_snapshot"].update(fields=[]),
            "period_report_template_invalid",
        ),
        (
            lambda value: value["template_snapshot"]["fields"].append({"id": "summary"}),
            "period_report_template_invalid",
        ),
        (
            lambda value: value["content"]["values"].update(summary="구형 요약"),
            "period_report_values_invalid",
        ),
    ],
)
def test_invalid_period_contract_is_rejected_before_model(mutation, error):
    source = sample()
    mutation(source)
    model = ScriptedModel(responses=[AIMessage(content="unused")])
    with pytest.raises(LLMError, match=error):
        asyncio.run(period.run(source, model=model))
    assert model._seen == []


def test_summary_is_not_part_of_period_output_contract():
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ReportDraftOutput.model_validate({**draft(), "summary": "중복 요약"})


def test_unexpected_model_error_is_sanitized():
    class BrokenModel(ScriptedModel):
        def _generate(self, *args, **kwargs):
            raise RuntimeError("private provider detail")

    with pytest.raises(LLMError, match="^period_report_agent_failed$") as error:
        asyncio.run(
            period.run(sample(), model=BrokenModel(responses=[AIMessage(content="unused")]))
        )
    assert error.value.__suppress_context__


def test_period_provider_error_keeps_worker_retry_code():
    request = httpx.Request("POST", "https://provider.invalid/v1/responses")
    response = httpx.Response(429, request=request)
    failure = openai.RateLimitError("private", response=response, body=None)

    class BrokenModel(ScriptedModel):
        def _generate(self, *args, **kwargs):
            raise failure

    with pytest.raises(LLMError, match="^llm_provider_error:429$"):
        asyncio.run(
            period.run(sample(), model=BrokenModel(responses=[AIMessage(content="unused")]))
        )


def test_period_uses_bounded_deep_agent_call_and_review_limits():
    assert period.REQUIRED_INITIAL_DELEGATIONS == 1
    assert period.MAX_REVIEWS == 2
    assert period.MAX_REPAIRS == 1
    assert period.MAX_SEMANTIC_REVIEWS == 1
    assert period.SUPERVISOR_MODEL_CALL_LIMIT == 4
    assert period.SUBAGENT_MODEL_CALL_LIMIT == 2
    assert period.REVIEWER_MODEL_CALL_LIMIT == 1
    assert period.MAX_MODEL_CALLS == 9
    assert period.MAX_STRUCTURAL_FAILURES == period.MAX_REVIEWS
