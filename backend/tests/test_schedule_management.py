import json

import pytest
from pydantic import ValidationError

from app.agents import schedule_management


def _input(**updates):
    values = {
        "sales_deal_id": "deal-1",
        "target_date": "2026-09-15",
        "target_time": None,
        "recommendation_status": "pending",
        "deal_outcome_code": "in_progress",
        "excluded_dates": [],
        "current_datetime": "2026-09-15T12:00:00+09:00",
        "timezone": "Asia/Seoul",
    }
    values.update(updates)
    return schedule_management._ScheduleLLMInput.model_validate(values)


def test_output_contract_is_closed():
    valid = {
        "decision": "valid",
        "reason_code": "recommendation_valid",
        "reason": "추천 날짜가 아직 유효합니다.",
    }
    assert schedule_management.ScheduleManagementOutput(**valid).decision == "valid"
    with pytest.raises(ValidationError):
        schedule_management.ScheduleManagementOutput(**valid, unexpected=True)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (_input(target_date="2026-09-14"), ("refresh_required", "target_date_passed")),
        (
            _input(target_time="11:00"),
            ("refresh_required", "target_time_passed"),
        ),
        (_input(recommendation_status="rejected"), ("refresh_required", "user_rejected")),
        (_input(recommendation_status="accepted"), ("ignored", "already_accepted")),
        (_input(deal_outcome_code="cancelled"), ("ignored", "deal_closed")),
        (_input(target_date="2026-09-16"), None),
        (_input(), None),
    ],
)
def test_required_decision(value, expected):
    assert schedule_management._required_decision(value) == expected


@pytest.mark.anyio
async def test_run_sends_only_validated_context_and_keeps_today_without_time(monkeypatch):
    captured = {}

    async def fake_generate_structured(**kwargs):
        captured.update(kwargs)
        # 명확한 날짜 비교는 LLM이 잘못 답해도 서버가 바로잡는다.
        return schedule_management.ScheduleManagementOutput(
            decision="refresh_required",
            reason_code="target_date_passed",
            reason="잘못된 판단",
        )

    monkeypatch.setattr(schedule_management, "generate_structured", fake_generate_structured)
    result = await schedule_management.run(
        {
            **_input().model_dump(mode="json"),
            "private_customer_note": "LLM으로 보내면 안 됨",
        }
    )

    assert result.decision == "valid"
    assert result.reason_code == "recommendation_valid"
    assert captured["schema"] is schedule_management.ScheduleManagementOutput
    assert captured["schema_name"] == "schedule_management"
    assert "private_customer_note" not in json.loads(captured["input_text"])


@pytest.mark.anyio
async def test_run_marks_past_target_for_refresh(monkeypatch):
    async def fake_generate_structured(**_kwargs):
        return schedule_management.ScheduleManagementOutput(
            decision="valid",
            reason_code="recommendation_valid",
            reason="아직 유효합니다.",
        )

    monkeypatch.setattr(schedule_management, "generate_structured", fake_generate_structured)
    result = await schedule_management.run(_input(target_date="2026-09-14").model_dump(mode="json"))

    assert result.decision == "refresh_required"
    assert result.reason_code == "target_date_passed"
