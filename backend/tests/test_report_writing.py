import pytest

from app.agents import report_writing


@pytest.mark.anyio
async def test_run_uses_report_prompt_and_input(monkeypatch):
    captured = {}

    async def fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return report_writing.ReportDraftOutput(fields=[], summary="초안")

    monkeypatch.setattr(report_writing, "generate_structured", fake_generate_structured)

    output = await report_writing.run(
        {
            "report_kind": "meeting",
            "report_date": "2026-08-21",
            "template_snapshot": {"fields": []},
            "content": {},
            "transcript": "고객이 다음 주에 견적서를 요청했다.",
            "guidance": None,
        }
    )

    assert output.summary == "초안"
    assert captured["instructions"] == report_writing.SYSTEM_PROMPT
    assert "미팅 기록: 고객이 다음 주에 견적서를 요청했다." in captured["input_text"]
    assert captured["schema"] is report_writing.ReportDraftOutput
    assert captured["schema_name"] == "report_draft"
