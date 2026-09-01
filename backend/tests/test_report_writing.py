import copy
from uuid import uuid4

import pytest

from app.agents import period_report_writing_deep, report_writing


@pytest.mark.anyio
async def test_run_uses_report_prompt_and_input(monkeypatch):
    captured = {}
    sales_deal_id = uuid4()

    async def fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return report_writing.ReportDraftOutput(
            fields=[report_writing.ReportDraftField(field_id="summary", value="미팅 초안")],
            summary="초안",
        )

    monkeypatch.setattr(report_writing, "generate_structured", fake_generate_structured)

    output = await report_writing.run(
        {
            "report_kind": "meeting",
            "report_date": "2026-08-21",
            "sales_deal_id": str(sales_deal_id),
            "template_snapshot": {"fields": [{"id": "summary", "label": "미팅 요약"}]},
            "content": {
                "summary": "",
                "sales_deal_ids": [str(sales_deal_id), str(uuid4())],
                "sales_deals": [{"id": str(sales_deal_id), "label": "DL-001"}],
            },
            "transcript": "고객이 다음 주에 견적서를 요청했다.",
            "guidance": None,
        }
    )

    assert output.summary == "초안"
    assert output.fields[0].field_id == "summary"
    assert captured["instructions"] == report_writing.SYSTEM_PROMPT
    assert (
        '보고서 양식(JSON): {"fields":[{"id":"summary","label":"미팅 요약"}]}'
        in captured["input_text"]
    )
    assert '현재 작성값(JSON): {"summary":""}' in captured["input_text"]
    assert f"대상 딜 ID: {sales_deal_id}" in captured["input_text"]
    assert "sales_deal_ids" not in captured["input_text"]
    assert "sales_deals" not in captured["input_text"]
    assert "미팅 기록: 고객이 다음 주에 견적서를 요청했다." in captured["input_text"]
    assert captured["schema"] is report_writing.ReportDraftOutput
    assert captured["schema_name"] == "report_draft"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "kind,field_ids",
    [
        ("daily", ["body"]),
        ("daily", ["summary", "activities", "issues", "next_plan"]),
        ("weekly", ["body"]),
        ("monthly", ["body"]),
        ("meeting", ["body"]),
    ],
)
async def test_period_reports_use_deep_agent_and_legacy_meeting_keeps_existing_path(
    monkeypatch, kind, field_ids
):
    captured = {}
    calls = []

    async def generate(**kwargs):
        calls.append("structured")
        captured.update(kwargs)
        return report_writing.ReportDraftOutput(
            fields=[
                {"field_id": field_id, "value": "기존 근거를 보존한 초안"} for field_id in field_ids
            ]
        )

    async def deep(snapshot):
        calls.append("deep")
        captured["snapshot"] = copy.deepcopy(snapshot)
        return report_writing.ReportDraftOutput(
            fields=[{"field_id": field_id, "value": "검토한 일일 초안"} for field_id in field_ids]
        )

    monkeypatch.setattr(report_writing, "generate_structured", generate)
    monkeypatch.setattr(period_report_writing_deep, "run", deep)
    snapshot = {
        "report_kind": kind,
        "report_date": "2026-08-31",
        "template_snapshot": {
            "id": "builtin-daily-freeform" if field_ids == ["body"] else "saved-template",
            "fields": [
                {"id": field_id, "label": "보고서 본문", "type": "textarea"}
                for field_id in field_ids
            ],
        },
        "content": {"values": {field_id: "사용자가 쓰던 내용" for field_id in field_ids}},
        "transcript": None,
        "guidance": None,
        "report_sources": {
            "reports": [{"values": {"body": "보안 승인 후 다음 주 도입 검토 예정이다."}}],
            "meetings": [
                {"unassigned_report": {"body": "딜 미지정 · 확인 필요: 그거 보내달랬다."}}
            ],
        },
    }
    original = copy.deepcopy(snapshot)

    output = await report_writing.run(snapshot)

    assert snapshot == original
    assert [field.field_id for field in output.fields] == field_ids
    if kind in {"daily", "weekly", "monthly"}:
        assert calls == ["deep"]
        assert captured["snapshot"] == original
    else:
        assert calls == ["structured"]
        assert captured["schema"] is report_writing.ReportDraftOutput
        assert "사용자가 쓰던 내용" in captured["input_text"]
        assert "보안 승인 후 다음 주 도입 검토 예정" not in captured["input_text"]
        assert "딜 미지정 · 확인 필요" not in captured["input_text"]
        assert "연결 보고서 자료" not in captured["instructions"]
        assert captured["instructions"] == report_writing.SYSTEM_PROMPT
