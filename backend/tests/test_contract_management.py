import pytest

from app.agents import contract_management


@pytest.mark.anyio
async def test_run_uses_structured_llm_boundary(monkeypatch):
    captured = {}
    expected = contract_management.ContractManagementOutput(
        contract_summary="계약 종료일 확인 필요",
        missing_information=["계약 종료일"],
        recommended_actions=["고객사와 갱신 일정 확인"],
    )

    async def fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(contract_management, "generate_structured", fake_generate_structured)
    result = await contract_management.run(
        {"customer_company": {"id": "company-1"}, "sales_deals": []}
    )

    assert result is expected
    assert captured["instructions"] == contract_management.SYSTEM_PROMPT
    assert captured["schema"] is contract_management.ContractManagementOutput
    assert captured["schema_name"] == "contract_management"
    assert "company-1" in captured["input_text"]


def test_output_rejects_unknown_severity():
    try:
        contract_management.ContractRisk(
            code="unresolved_support",
            severity="critical",
            message="위험",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("허용되지 않은 심각도를 받아들였습니다")


def test_output_rejects_unknown_risk_code():
    try:
        contract_management.ContractRisk(
            code="made_up_risk",
            severity="high",
            message="위험",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("정의되지 않은 위험 코드를 받아들였습니다")
