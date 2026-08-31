from uuid import uuid4

import pytest

from app.agents import report_writing


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
