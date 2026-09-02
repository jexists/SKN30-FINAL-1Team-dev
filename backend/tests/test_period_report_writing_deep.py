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


def test_actual_graph_reads_sources_revises_and_returns_accepted_draft_unchanged():
    source = sample()
    original = copy.deepcopy(source)
    good = draft()
    bad = draft()
    bad["fields"][0]["value"] = "합성회사 A의 예산이 승인되었다."
    model = ScriptedModel(
        responses=[
            call("read_report_sources"),
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


def test_subagent_reads_only_target_meeting_with_common_and_unassigned(monkeypatch):
    import deepagents.middleware.subagents

    specs = []
    original = deepagents.middleware.subagents.create_sub_agent

    def record_subagent(spec, **kwargs):
        specs.append(spec)
        return original(spec, **kwargs)

    monkeypatch.setattr(deepagents.middleware.subagents, "create_sub_agent", record_subagent)
    source = sample()
    model = ScriptedModel(
        responses=[
            call("read_report_sources"),
            call("task", subagent_type="general-purpose", description="합성회사 A 미팅 초안"),
            call("read_report_sources", activity_id=str(MEETING_A)),
            AIMessage(content="A의 두 딜과 공통·미지정 내용을 함께 정리한다."),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )

    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == draft()
    shared = json.loads(model._seen[1][-1].content)
    scoped = json.loads(model._seen[3][-1].content)
    assert shared["report_sources"] == source["report_sources"]
    assert shared["current_values"] == source["content"]["values"]
    assert shared["transcript"] == source["transcript"]
    assert scoped["report_sources"]["reports"] == source["report_sources"]["reports"][:2]
    assert scoped["report_sources"]["meetings"] == source["report_sources"]["meetings"][:1]
    assert scoped["current_values"] == {}
    assert scoped["transcript"] is None
    assert scoped["activities"] == scoped["attachments"] == []
    assert "그것도 보내주세요" in str(scoped)
    assert "합성회사 B" not in str(scoped)
    assert specs
    for spec in specs:
        assert {
            tool.name if hasattr(tool, "name") else tool.__name__ for tool in spec["tools"]
        } == {"read_report_sources"}
        assert not any("finish_accepted" in item.name for item in spec.get("middleware", []))


def test_unknown_meeting_cannot_read_other_meeting_sources():
    model = ScriptedModel(
        responses=[
            call("read_report_sources", activity_id=str(UUID(int=999))),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )
    asyncio.run(period.run(sample(), model=model))
    result = json.loads(model._seen[1][-1].content)
    assert result.get("error")
    assert "합성회사" not in str(result)


@pytest.mark.parametrize("invalid", ["duplicate", "missing", "unexpected", "blank_body"])
def test_structural_field_errors_are_repaired_before_semantic_review(invalid):
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
            call("review_period_report", draft=bad),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )

    assert asyncio.run(period.run(sample(), model=model)).model_dump(mode="json") == draft()
    assert len(model._seen) == 3  # 잘못된 필드는 의미 검토 모델에 보내지 않는다.
    feedback = json.loads(model._seen[1][-1].content)
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
        responses=[call("review_period_report", draft=good), call("ReportReview", issues=[])]
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
            call("read_report_sources"),
            call("review_period_report", draft=good),
            call("ReportReview", issues=[]),
        ]
    )
    assert asyncio.run(period.run(source, model=model)).model_dump(mode="json") == good
    assert source["transcript"] in str(model._seen[-1])


def test_direct_final_output_cannot_skip_semantic_review():
    model = ScriptedModel(
        responses=[
            call("ReportDraftOutput", **draft()),
            call("ReportReview", issues=["검토 예정이라는 조건을 분명히 보존하라."]),
            call("ReportDraftOutput", **draft()),
            call("ReportReview", issues=[]),
        ]
    )
    assert asyncio.run(period.run(sample(), model=model)).model_dump(mode="json") == draft()
    assert len(model._seen) == 4
    assert "검토 예정이라는 조건" in str(model._seen[2])


def test_direct_final_submission_repairs_structure_and_passes_semantic_review():
    bad = draft()
    bad["fields"][0]["field_id"] = "other"
    model = ScriptedModel(
        responses=[
            call("ReportDraftOutput", **bad),
            call("ReportDraftOutput", **draft()),
            call("ReportReview", issues=[]),
        ]
    )
    assert asyncio.run(period.run(sample(), model=model)).model_dump(mode="json") == draft()
    assert len(model._seen) == 3
    assert "expected_ids" in str(model._seen[1])


def test_review_limit_does_not_keep_retrying(monkeypatch):
    monkeypatch.setattr(writer, "MAX_REVIEWS", 2)
    model = ScriptedModel(
        responses=[
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=["원문의 조건을 보존하라."]),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=["원문의 조건을 보존하라."]),
            call("review_period_report", draft=draft()),
        ]
    )
    with pytest.raises(LLMError, match="^period_report_agent_review_limit$"):
        asyncio.run(period.run(sample(), model=model))
    assert len(model._seen) == 5


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
            call("read_report_sources"),
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
    shared = json.loads(model._seen[1][-1].content)
    reviewed = json.loads(model._seen[2][-1].content)["source"]
    for supplied in (shared, reviewed):
        assert supplied["report_kind"] == kind
        assert supplied["period_start"] == source["period_start"]
        assert supplied["period_end"] == source["period_end"]
        assert supplied["report_sources"] == source["report_sources"]
    if kind == "monthly":
        boundary = reviewed["report_sources"]["reports"][0]
        assert boundary["period_start"] < reviewed["period_start"]
        assert "각 문의의 날짜는 기록되지 않았다" in boundary["values"]["body"]
        assert "미승인" in result.fields[0].value


@pytest.mark.parametrize("kind", ["daily", "weekly", "monthly"])
def test_read_one_selected_report_keeps_only_its_sources(kind):
    source = sample() if kind == "daily" else period_sample(kind)
    selected = source["report_sources"]["reports"][0]
    good = draft()
    model = ScriptedModel(
        responses=[
            call("read_report_sources", report_id=selected["id"]),
            call("review_period_report", draft=good),
            call("ReportReview", issues=[]),
        ]
    )

    asyncio.run(period.run(source, model=model))

    scoped = json.loads(model._seen[1][-1].content)
    assert scoped["report_sources"]["reports"] == [selected]
    expected_meetings = source["report_sources"]["meetings"][:1] if kind == "daily" else []
    assert scoped["report_sources"]["meetings"] == expected_meetings
    assert scoped["current_values"] == {}
    assert scoped["transcript"] is None
    assert scoped["activities"] == scoped["attachments"] == []


@pytest.mark.parametrize(
    ("kind", "filters"),
    [
        ("daily", {"activity_id": str(MEETING_A), "report_id": str(UUID(int=201))}),
        ("weekly", {"activity_id": str(MEETING_A)}),
        ("monthly", {"activity_id": str(MEETING_A)}),
        ("daily", {"report_id": str(UUID(int=999))}),
        ("weekly", {"report_id": str(UUID(int=999))}),
        ("monthly", {"report_id": str(UUID(int=999))}),
    ],
    ids=[
        "daily-both-filters-rejected",
        "weekly-activity-not-selected",
        "monthly-activity-not-selected",
        "daily-report-not-selected",
        "weekly-report-not-selected",
        "monthly-report-not-selected",
    ],
)
def test_conflicting_or_unselected_source_filters_do_not_expose_reports(kind, filters):
    source = sample() if kind == "daily" else period_sample(kind)
    model = ScriptedModel(
        responses=[
            call("read_report_sources", **filters),
            call("review_period_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )
    asyncio.run(period.run(source, model=model))
    result = json.loads(model._seen[1][-1].content)
    assert result.get("error")
    assert "report_sources" not in result
    assert "합성" not in str(result)
    if filters.get("report_id") == str(UUID(int=999)):
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
