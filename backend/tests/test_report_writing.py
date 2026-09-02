import copy

import pytest

from app.agents import period_report_writing_deep, report_writing
from app.services.llm import LLMError


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["daily", "weekly", "monthly"])
async def test_report_writer_dispatches_only_period_kinds_without_mutating_snapshot(
    monkeypatch, kind
):
    captured = {}

    async def write_period(snapshot):
        captured["snapshot"] = copy.deepcopy(snapshot)
        return report_writing.ReportDraftOutput(
            fields=[{"field_id": "body", "value": "검토한 기간 보고서"}]
        )

    monkeypatch.setattr(period_report_writing_deep, "run", write_period)
    snapshot = {
        "report_kind": kind,
        "report_date": "2026-08-31",
        "template_snapshot": {"fields": [{"id": "body", "type": "textarea", "aiFilled": True}]},
        "content": {"values": {"body": "사용자가 쓰던 내용"}},
    }
    original = copy.deepcopy(snapshot)

    result = await report_writing.run(snapshot)

    assert result.fields[0].value == "검토한 기간 보고서"
    assert captured["snapshot"] == original
    assert snapshot == original


@pytest.mark.anyio
async def test_report_writer_rejects_legacy_meeting_path_before_dispatch(monkeypatch):
    called = False

    async def write_period(snapshot):
        nonlocal called
        called = True

    monkeypatch.setattr(period_report_writing_deep, "run", write_period)
    with pytest.raises(LLMError, match="^report_writing_kind_unsupported$"):
        await report_writing.run({"report_kind": "meeting"})
    assert called is False


def test_report_output_contains_only_generated_fields():
    output = report_writing.ReportDraftOutput(
        fields=[report_writing.ReportDraftField(field_id="body", value="초안")]
    )
    assert output.model_dump() == {"fields": [{"field_id": "body", "value": "초안"}]}
