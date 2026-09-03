"""미팅 보고서의 Deep Agent 계획·위임·검토 경로를 외부 통신 없이 검사한다."""

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


def calls(*items):
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": str(uuid4())} for name, args in items],
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
                "body": "A는 보안 승인을 받은 뒤 예산을 검토할 예정입니다.",
                "evidence_ids": ["S0002"],
            },
            {
                "sales_deal_id": str(DEAL_B),
                "title": writer.NO_DEAL_EVIDENCE_TEXT,
                "body": writer.NO_DEAL_EVIDENCE_TEXT,
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


def delegated_writing_responses(*, read_examples=False):
    deal_a_reads = [
        ("read_meeting_evidence", {"sales_deal_id": str(DEAL_A)}),
        ("read_deal_crm", {"sales_deal_id": str(DEAL_A)}),
        ("read_previous_reports", {"sales_deal_id": str(DEAL_A)}),
    ]
    if read_examples:
        deal_a_reads.insert(
            0,
            (
                "read_file",
                {
                    "file_path": "/skills/meeting/sales-meeting-report/references/examples.md",
                    "limit": 1000,
                },
            ),
        )
    return [
        call(
            "task",
            subagent_type="general-purpose",
            description=f"sales_deal_id={DEAL_A}\n해당 딜의 title과 body를 작성하세요.",
        ),
        calls(*deal_a_reads),
        AIMessage(content="보안 승인 후 예산 검토 예정이며 근거는 S0002입니다."),
        call(
            "task",
            subagent_type="general-purpose",
            description=f"sales_deal_id={DEAL_B}\n해당 딜의 title과 body를 작성하세요.",
        ),
        calls(
            ("read_meeting_evidence", {"sales_deal_id": str(DEAL_B)}),
            ("read_deal_crm", {"sales_deal_id": str(DEAL_B)}),
            ("read_previous_reports", {"sales_deal_id": str(DEAL_B)}),
        ),
        AIMessage(content=writer.NO_DEAL_EVIDENCE_TEXT),
        call(
            "task",
            subagent_type="general-purpose",
            description="section=common_unassigned\n공통·딜 미지정 본문을 작성하세요.",
        ),
        call("read_meeting_evidence"),
        AIMessage(content="공통 미팅과 대상이 불명확한 요청을 합니다체로 작성했습니다."),
    ]


def delegated_repair_responses(marker):
    if marker == f"sales_deal_id={DEAL_A}":
        return [
            call(
                "task",
                subagent_type="general-purpose",
                description=f"repair_{marker}\n검토에서 지적된 A 딜 문장만 다시 작성하세요.",
            ),
            calls(
                ("read_meeting_evidence", {"sales_deal_id": str(DEAL_A)}),
                ("read_deal_crm", {"sales_deal_id": str(DEAL_A)}),
                ("read_previous_reports", {"sales_deal_id": str(DEAL_A)}),
            ),
            AIMessage(content="A 딜의 지적된 문장만 조건부 표현으로 복원했습니다."),
        ]
    if marker == "section=common_unassigned":
        return [
            call(
                "task",
                subagent_type="general-purpose",
                description="repair_section=common_unassigned\n공통·미지정 부분만 다시 작성하세요.",
            ),
            call("read_meeting_evidence"),
            AIMessage(content="공통·미지정 부분만 다시 작성했습니다."),
        ]
    raise AssertionError(f"지원하지 않는 테스트 repair marker: {marker}")


def test_actual_deep_agent_reads_skill_and_examples_delegates_and_revises():
    source = sample()
    histories = [
        {
            "sales_deal_id": str(deal),
            "items": [{"report_id": str(uuid4()), "values": {"body": f"딜 {deal} 과거 기록"}}],
        }
        for deal in (DEAL_A, DEAL_B)
    ]
    product_context = [
        {
            "kind": "product_details",
            "sales_deal_id": str(deal),
            "data": {"name": f"딜 {deal} 전용 제품"},
        }
        for deal in (DEAL_A, DEAL_B)
    ]
    source.crm_context.update(
        deals=[
            {"sales_deal_id": str(deal), "title": f"딜 {deal} CRM"} for deal in (DEAL_A, DEAL_B)
        ],
        previous_reports=histories,
        additional_context=[*product_context, {"kind": "product_details", "items": ["공용 아님"]}],
    )
    original = source.model_dump(mode="json")
    bad = draft()
    bad["deal_reports"][0]["body"] = "A의 예산은 승인되었습니다."
    model = ScriptedModel(
        responses=[
            *delegated_writing_responses(read_examples=True),
            call("review_report", draft=bad),
            call(
                "ReportReview",
                issues=["deal_reports[0].body: 예산 승인으로 강화된 조건을 원문대로 복원하라."],
            ),
            *delegated_repair_responses(f"sales_deal_id={DEAL_A}"),
            call("review_report", draft=draft()),
        ]
    )

    result = asyncio.run(writer.run(source, model=model))

    assert result.model_dump(mode="json") == draft()
    assert source.model_dump(mode="json") == original
    assert len(model._seen) == 15
    assert "딜 미지정 · 확인 필요" not in result.unassigned_report.body
    assert "out_of_scope" not in result.unassigned_report.body

    skill = (writer.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "[합성 작성 예시](references/examples.md)" in skill
    subagent_prompts = [
        str(messages[0].content)
        for messages in model._seen
        if "너는 실제 보고서 문장을 쓰는 하위 작성자다" in str(messages[0].content)
    ]
    assert subagent_prompts
    assert all(skill in prompt for prompt in subagent_prompts)
    examples_receipt = next(
        message
        for messages in model._seen
        for message in messages
        if message.type == "tool"
        and message.name == "read_file"
        and "보안 검토 선행·예산 미승인" in message.content
    )
    assert "내일 보안 체크리스트를 전달하기로 했습니다" in examples_receipt.content
    assert "영업담당자는 내일" not in examples_receipt.content

    tool_payloads: dict[str, list[dict]] = {}
    for messages in model._seen:
        for message in messages:
            if message.type != "tool" or message.name not in {
                "read_meeting_evidence",
                "read_deal_crm",
                "read_previous_reports",
            }:
                continue
            tool_payloads.setdefault(message.name, []).append(json.loads(message.content))
    evidence_a = next(
        payload
        for payload in tool_payloads["read_meeting_evidence"]
        if {item["segment"]["segment_id"] for item in payload["evidence"]} == {"S0001", "S0002"}
    )
    evidence_b = next(
        payload
        for payload in tool_payloads["read_meeting_evidence"]
        if {item["segment"]["segment_id"] for item in payload["evidence"]} == {"S0001"}
    )
    crm_a = next(
        payload
        for payload in tool_payloads["read_deal_crm"]
        if payload["crm_context"]["deals"][0]["sales_deal_id"] == str(DEAL_A)
    )
    history_a = next(
        payload
        for payload in tool_payloads["read_previous_reports"]
        if payload["previous_reports"][0]["sales_deal_id"] == str(DEAL_A)
    )
    assert {item["segment"]["segment_id"] for item in evidence_a["evidence"]} == {
        "S0001",
        "S0002",
    }
    assert {item["segment"]["segment_id"] for item in evidence_b["evidence"]} == {"S0001"}
    assert crm_a["crm_context"]["deals"] == [source.crm_context["deals"][0]]
    assert crm_a["crm_context"]["additional_context"] == [product_context[0]]
    assert "previous_reports" not in crm_a["crm_context"]
    assert history_a == {"previous_reports": [histories[0]]}
    assert any("예산 승인으로 강화된 조건" in str(messages) for messages in model._seen)

    main_tools = next(names for names in model._tool_sets if "review_report" in names)
    assert {"read_file", "write_file", "task", "review_report"} <= main_tools
    assert (
        not {
            "read_meeting_evidence",
            "read_deal_crm",
            "read_previous_reports",
        }
        & main_tools
    )
    subagent_tools = next(names for names in model._tool_sets if "read_deal_crm" in names)
    assert {"read_meeting_evidence", "read_deal_crm", "read_previous_reports"} <= subagent_tools
    assert "review_report" not in subagent_tools
    assert all(not {"execute", "web_search"} & names for names in model._tool_sets)
    system_prompt = str(model._seen[0][0].content)
    assert "직접 보고서 문장을 쓰거나" in system_prompt
    assert "# 영업 미팅 보고서 작성" not in system_prompt
    assert "sales-meeting-report 스킬을 읽고" not in system_prompt
    assert "원문·CRM·작성 스킬을 읽지 말고" in system_prompt
    assert "합니다체로 통일한다" not in system_prompt


def test_direct_submission_without_required_tasks_is_not_reviewed():
    model = ScriptedModel(
        responses=[
            call("FreeformMeetingReports", **draft()),
            *delegated_writing_responses(),
            call("FreeformMeetingReports", **draft()),
            call("ReportReview", issues=[]),
        ]
    )

    result = asyncio.run(writer.run(sample(), model=model))

    assert result.model_dump(mode="json") == draft()
    assert "report_agent_delegation_missing" not in str(model._seen)
    assert any("작성 task를 성공적으로 완료" in str(messages) for messages in model._seen)
    assert len(model._seen) == 12


def test_structural_issue_is_repaired_before_semantic_review(monkeypatch):
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
            *delegated_writing_responses(),
            call("review_report", draft=bad),
            call("ReportReview", issues=[]),
            *delegated_repair_responses("section=common_unassigned"),
            call("review_report", draft=draft()),
        ]
    )

    result = asyncio.run(writer.run(sample(), model=model))

    assert result.model_dump(mode="json") == draft()
    summary = next(item for item in progress if item["stage"] == "report_writing.summary")
    assert summary["semantic_review_count"] == 1
    assert summary["validation_attempt"] == 2
    assert summary["delegation_count"] == 4
    assert summary["model_call_count"] == 15
    assert summary["tool_call_count"] > summary["delegation_count"]
    assert summary["tool_call_count"] != summary["call_count"]
    assert summary["repair_count"] == 1


def test_remaining_quality_issue_after_one_repair_returns_renderable_draft():
    bad = draft()
    bad["unassigned_report"] = None
    model = ScriptedModel(
        responses=[
            *delegated_writing_responses(),
            call("review_report", draft=bad),
            call("ReportReview", issues=[]),
            *delegated_repair_responses("section=common_unassigned"),
            call("review_report", draft=bad),
        ]
    )

    result = asyncio.run(writer.run(sample(), model=model))

    assert result.model_dump(mode="json") == bad


def test_accepted_review_finishes_without_another_parent_model_call():
    model = ScriptedModel(
        responses=[
            *delegated_writing_responses(),
            call("review_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )

    result = asyncio.run(writer.run(sample(), model=model))

    assert result.model_dump(mode="json") == draft()
    assert len(model._seen) == 11


def test_accepted_review_returns_normalized_deal_order():
    reversed_draft = draft()
    reversed_draft["deal_reports"].reverse()
    model = ScriptedModel(
        responses=[
            *delegated_writing_responses(),
            call("review_report", draft=reversed_draft),
            call("ReportReview", issues=[]),
        ]
    )

    result = asyncio.run(writer.run(sample(), model=model))

    assert result.model_dump(mode="json") == draft()


def test_candidate_preview_is_filtered_to_selected_sections(monkeypatch):
    events = []
    monkeypatch.setattr(
        writer, "publish_progress", lambda stage=None, **kwargs: events.append(kwargs)
    )
    budget = writer._MeetingRunBudget([DEAL_A, DEAL_B], model_call_limit=20)
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


def test_shared_model_budget_caps_parent_subagent_and_reviewer(monkeypatch):
    monkeypatch.setattr(writer, "_run_model_call_limit", lambda _required: 3)
    model = ScriptedModel(
        responses=[
            call(
                "task",
                subagent_type="general-purpose",
                description=f"sales_deal_id={DEAL_A}\n해당 딜 초안을 작성하세요.",
            ),
            AIMessage(content="A 딜 초안"),
            call("review_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )
    with pytest.raises(LLMError, match="^report_agent_model_call_limit$"):
        asyncio.run(writer.run(sample(), model=model))
    assert len(model._seen) == 3
