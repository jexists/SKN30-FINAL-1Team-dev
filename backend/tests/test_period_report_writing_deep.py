"""기간 보고서의 bounded source units와 고정 작성·검토 경로를 검사한다."""

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
from app.agents import report_writing_deep as meeting_writer
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
                "value": "합성회사 A의 구매팀과 미팅했다. 보안 제품은 보안 승인 후 예산을 "
                "검토할 예정이며, 운영 제품은 가격 비교 자료를 요청했다. ‘그것도 보내주세요.’는 "
                "대상 딜이 불명확하여 확인이 필요하다.\n\n"
                "합성회사 B의 기술팀과 온라인으로 만났다. 분석 제품은 기술팀 검토 중이며 "
                "도입은 아직 확정되지 않았다.",
            }
        ]
    }


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


def test_pipeline_writes_and_reviews_once_with_all_units_inline():
    model = ScriptedModel(
        responses=[call("ReportDraftOutput", **draft()), call("ReportReview", issues=[])]
    )

    result = asyncio.run(period.run(sample(), model=model))

    assert result.model_dump(mode="json") == draft()
    assert len(model._seen) == 2
    assert model._tool_sets == [{"ReportDraftOutput"}, {"ReportReview"}]
    payload = json.loads(model._seen[0][-1].content)
    assert len(payload["source"]["source_units"]) == 2
    assert "보안 승인 후 예산" in str(payload["source"]["source_units"])


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
            call("ReportDraftOutput", **bad),
            call("ReportReview", issues=[]),
            call("ReportDraftOutput", **draft()),
        ]
    )

    result = asyncio.run(period.run(source, model=model))

    assert result.model_dump(mode="json") == draft()
    repair = json.loads(model._seen[2][-1].content)
    assert repair["issues"][0]["expected_ids"] == ["body"]
    assert repair["issues"][0]["actual_ids"] == ["body", "manager_note"]


def test_semantic_issue_causes_one_repair_and_no_second_review():
    bad = copy.deepcopy(draft())
    bad["fields"][0]["value"] = "두 회사 모두 구매를 확정했다."
    model = ScriptedModel(
        responses=[
            call("ReportDraftOutput", **bad),
            call("ReportReview", issues=["확정 근거가 없으므로 조건과 미확정을 복원하라."]),
            call("ReportDraftOutput", **draft()),
        ]
    )

    result = asyncio.run(period.run(sample(), model=model))

    assert result.model_dump(mode="json") == draft()
    assert len(model._seen) == 3
    assert json.loads(model._seen[2][-1].content)["issues"] == [
        "확정 근거가 없으므로 조건과 미확정을 복원하라."
    ]


def test_repair_must_pass_final_ai_field_validation():
    bad = {"fields": [{"field_id": "wrong", "value": "잘못된 필드"}]}
    model = ScriptedModel(
        responses=[
            call("ReportDraftOutput", **bad),
            call("ReportReview", issues=[]),
            call("ReportDraftOutput", **bad),
        ]
    )
    with pytest.raises(LLMError, match="period_report_agent_structural_limit"):
        asyncio.run(period.run(sample(), model=model))


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


def test_period_uses_same_single_review_and_repair_limits():
    assert meeting_writer.MAX_REVIEWS == 1
    assert meeting_writer.MAX_REPAIRS == 1
    assert meeting_writer.MAX_STRUCTURAL_ATTEMPTS == 2
