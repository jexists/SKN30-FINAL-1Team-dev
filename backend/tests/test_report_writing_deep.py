"""미팅 보고서의 고정 작성 → 검토 → 1회 수정 경로를 외부 통신 없이 검사한다."""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from pydantic import PrivateAttr

from app.agents import report_writing_deep as writer
from app.schemas.meeting_content import (
    MeetingContentAnalysisOutput,
    MeetingContentInput,
    build_evidence_ledger,
)
from app.services.llm import LLMError

DEAL_A = UUID(int=1)
DEAL_B = UUID(int=2)


class ScriptedModel(FakeMessagesListChatModel):
    _seen: list = PrivateAttr(default_factory=list)
    _tool_sets: list = PrivateAttr(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        self._tool_sets.append(
            {tool.name if hasattr(tool, "name") else tool["function"]["name"] for tool in tools}
        )
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._seen.append(messages)
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def call(name, **args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": str(uuid4())}])


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
    return writer.ReportWritingInput(
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
                "body": "A는 보안 승인을 받은 뒤 예산을 검토할 예정이다.",
                "evidence_ids": ["S0002"],
            },
            {
                "sales_deal_id": str(DEAL_B),
                "title": writer.NO_DEAL_EVIDENCE_TEXT,
                "body": writer.NO_DEAL_EVIDENCE_TEXT,
                "evidence_ids": [],
            },
        ],
        "common_report": {"body": "구매팀과 미팅을 진행했다.", "evidence_ids": ["S0001"]},
        "unassigned_report": {
            "body": "딜 미지정 · 확인 필요: ‘그거 다시 보내달래.’, ‘기타 메모 ???’. "
            "대상 딜과 의미를 확인해야 한다.",
            "evidence_ids": ["S0003", "S0004"],
        },
    }


def test_pipeline_writes_once_and_reviews_once_without_runtime_tools():
    source = sample()
    original = source.model_dump(mode="json")
    model = ScriptedModel(
        responses=[
            call("FreeformMeetingReports", **draft()),
            call("ReportReview", issues=[]),
        ]
    )

    result = asyncio.run(writer.run(source, model=model))

    assert result.model_dump(mode="json") == draft()
    assert source.model_dump(mode="json") == original
    assert len(model._seen) == 2
    assert model._tool_sets == [{"FreeformMeetingReports"}, {"ReportReview"}]
    writer_input = json.loads(model._seen[0][-1].content)
    assert writer_input["source"]["evidence"]["selected_deal_ids"] == [str(DEAL_A), str(DEAL_B)]
    system_prompt = model._seen[0][0].content
    assert "독자는 미팅에 참석하지 않은 영업팀장·임원" in system_prompt
    assert "crm_context에 동결되어 제공된 previous_reports" in system_prompt
    assert "read_previous_reports" not in system_prompt


def test_semantic_issue_causes_exactly_one_repair():
    bad = draft()
    bad["deal_reports"][0]["body"] = "A의 예산은 승인됐다."
    model = ScriptedModel(
        responses=[
            call("FreeformMeetingReports", **bad),
            call("ReportReview", issues=["예산 승인 사실이 없으므로 조건부 표현을 복원하라."]),
            call("FreeformMeetingReports", **draft()),
        ]
    )

    result = asyncio.run(writer.run(sample(), model=model))

    assert result.model_dump(mode="json") == draft()
    assert len(model._seen) == 3
    repair = json.loads(model._seen[2][-1].content)
    assert repair["draft"]["deal_reports"][0]["body"] == "A의 예산은 승인됐다."
    assert repair["issues"] == ["예산 승인 사실이 없으므로 조건부 표현을 복원하라."]


def test_structural_issue_has_separate_attempt_and_one_semantic_review(monkeypatch):
    bad = draft()
    bad["unassigned_report"] = None
    progress = []
    monkeypatch.setattr(
        writer,
        "log_agent_event",
        lambda stage, **fields: progress.append({"stage": stage, **fields}),
    )
    model = ScriptedModel(
        responses=[
            call("FreeformMeetingReports", **bad),
            call("ReportReview", issues=[]),
            call("FreeformMeetingReports", **draft()),
        ]
    )

    result = asyncio.run(writer.run(sample(), model=model))

    assert result.model_dump(mode="json") == draft()
    summary = next(item for item in progress if item["stage"] == "report_writing.summary")
    assert summary["semantic_review_count"] == 1
    assert summary["validation_attempt"] == 2
    assert summary["repair_count"] == 1


def test_repair_must_pass_final_structural_validation():
    bad = draft()
    bad["unassigned_report"] = None
    model = ScriptedModel(
        responses=[
            call("FreeformMeetingReports", **bad),
            call("ReportReview", issues=[]),
            call("FreeformMeetingReports", **bad),
        ]
    )

    with pytest.raises(LLMError, match="^report_agent_structural_limit$"):
        asyncio.run(writer.run(sample(), model=model))


def test_candidate_preview_is_filtered_to_selected_sections(monkeypatch):
    events = []
    monkeypatch.setattr(
        writer, "publish_progress", lambda stage=None, **kwargs: events.append(kwargs)
    )
    budget = writer._RunBudget([DEAL_A, DEAL_B])
    budget.preview(
        {
            "deal_reports": [
                {"sales_deal_id": str(DEAL_B), "body": "B 초안"},
                {"sales_deal_id": str(UUID(int=99)), "body": "선택하지 않은 딜"},
            ],
            "common_report": {"body": "공통 초안"},
            "unassigned_report": {"body": "미지정 초안"},
        }
    )
    budget.preview({"unassigned_report": None})

    previews = [item["preview"] for item in events]
    assert [(item["section"], item["sales_deal_id"]) for item in previews] == [
        ("deal", str(DEAL_B)),
        ("common", None),
        ("unassigned", None),
        ("unassigned", None),
    ]
    assert [item["body"] for item in previews] == ["B 초안", "공통 초안", "미지정 초안", ""]
    assert [item["revision"] for item in previews] == [1, 2, 3, 4]
    assert "선택하지 않은 딜" not in str(previews)


def test_run_timeout_and_unexpected_error_are_sanitized(monkeypatch):
    class SlowModel(ScriptedModel):
        async def _agenerate(self, messages, **kwargs):
            await asyncio.sleep(1)
            return self._generate(messages, **kwargs)

    monkeypatch.setattr(writer, "RUN_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(LLMError, match="^report_agent_timeout$"):
        asyncio.run(writer.run(sample(), model=SlowModel(responses=[AIMessage(content="wait")])))

    class BrokenModel(ScriptedModel):
        def _generate(self, *args, **kwargs):
            raise RuntimeError("provider secret and private transcript")

    monkeypatch.setattr(writer, "RUN_TIMEOUT_SECONDS", 180)
    with pytest.raises(LLMError, match="^report_agent_failed$") as error:
        asyncio.run(
            writer.run(sample(), model=BrokenModel(responses=[AIMessage(content="unused")]))
        )
    assert error.value.__suppress_context__


def test_shared_model_budget_still_caps_all_fixed_calls(monkeypatch):
    monkeypatch.setattr(writer, "MAX_MODEL_CALLS", 1)
    model = ScriptedModel(
        responses=[
            call("FreeformMeetingReports", **draft()),
            call("ReportReview", issues=[]),
        ]
    )
    with pytest.raises(LLMError, match="^report_agent_model_call_limit$"):
        asyncio.run(writer.run(sample(), model=model))
