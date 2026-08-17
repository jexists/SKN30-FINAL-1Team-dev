import asyncio
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.schemas.contract_briefing import (
    ApprovedMeetingInsight,
    ContractEvidenceBundle,
    ContractRiskAssessment,
    NextMeetingCandidate,
    RiskItem,
)
from app.schemas.sales_deals import SalesDealRead
from app.services.contract_briefing_llm import (
    AnthropicContractBriefingSynthesizer,
    MockContractBriefingSynthesizer,
    get_contract_briefing_synthesizer,
)

TODAY = date(2026, 8, 17)


def _make_contract(**overrides) -> SalesDealRead:
    defaults = dict(
        id=uuid4(),
        deal_no="FM-DL-TEST-0001",
        customer_company_id=uuid4(),
        customer_company_name="테스트 병원",
        customer_company_region_code=None,
        customer_contact_id=None,
        customer_contact_name=None,
        owner_member_id=uuid4(),
        owner_display_name="김지훈",
        product_id=None,
        product_name=None,
        sales_pipeline_id=uuid4(),
        sales_pipeline_name="기본 파이프라인",
        sales_pipeline_status_code="published",
        sales_pipeline_is_default=True,
        sales_pipeline_stage_id=uuid4(),
        sales_pipeline_stage_code="sent",
        sales_pipeline_stage_name="계약서 발송",
        sales_pipeline_stage_tone="orange",
        sales_pipeline_stage_phase_code="contract",
        sales_pipeline_stage_outcome_code="in_progress",
        sales_pipeline_stage_position=3,
        sales_deal_type_id=uuid4(),
        deal_type_code="new_installation",
        deal_type_name="신규 설치",
        title="테스트 계약",
        description=None,
        deal_amount=10_000_000,
        opened_on=date(2026, 1, 1),
        closed_on=None,
        quote_no=None,
        quote_issued_on=None,
        quote_valid_until=None,
        contract_no="FM-CT-TEST-0001",
        contract_signed_on=None,
        contract_ends_on=None,
        warranty_terms=None,
        expected_delivery_at=None,
        memo=None,
        stage_position=0,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    defaults.update(overrides)
    return SalesDealRead(**defaults)


def _bundle(*, risks=None, is_needed=False, candidate_date=None, insight=None):
    return ContractEvidenceBundle(
        contract=_make_contract(),
        risk_assessment=ContractRiskAssessment(
            risks=risks or [],
            next_meeting=NextMeetingCandidate(
                is_needed=is_needed, candidate_date=candidate_date, triggered_by=[]
            ),
        ),
        approved_meeting_insight=insight,
    )


def _synthesize(bundle: ContractEvidenceBundle):
    return asyncio.run(MockContractBriefingSynthesizer().synthesize(bundle))


_HIGH_RISK = RiskItem(
    kind="expiry",
    severity="high",
    message="계약 만료까지 15일 남았습니다.",
    evidence={"days_left": 15},
)
_MEDIUM_RISK = RiskItem(
    kind="delivery",
    severity="medium",
    message="납품 예정일이 3일 남았습니다.",
    evidence={"days_left": 3},
)


# ---- 우선순위 판단 ----


def test_no_risk_and_no_meeting_needed_is_low_priority():
    result = _synthesize(_bundle())
    assert result.priority == "low"
    assert "위험 신호와 접촉 공백이 모두 없습니다" in result.priority_reason


def test_no_risk_but_meeting_needed_is_still_low_priority_with_different_reason():
    result = _synthesize(_bundle(is_needed=True, candidate_date=TODAY))
    assert result.priority == "low"
    assert "접촉 공백이 있어" in result.priority_reason


def test_priority_matches_highest_severity_risk():
    result = _synthesize(
        _bundle(risks=[_MEDIUM_RISK, _HIGH_RISK], is_needed=True, candidate_date=TODAY)
    )
    assert result.priority == "high"
    assert "expiry" in result.priority_reason


# ---- narrative ----


def test_narrative_lists_all_risk_messages():
    result = _synthesize(_bundle(risks=[_MEDIUM_RISK, _HIGH_RISK]))
    assert _HIGH_RISK.message in result.narrative
    assert _MEDIUM_RISK.message in result.narrative


def test_narrative_notes_pending_integration_without_insight():
    result = _synthesize(_bundle())
    assert "연동 대기" in result.narrative


def test_narrative_includes_next_meeting_candidate_date():
    result = _synthesize(_bundle(is_needed=True, candidate_date=TODAY))
    assert str(TODAY) in result.narrative


# ---- approved_meeting_insight 반영 ----


def test_insight_needs_and_barriers_appear_in_narrative_and_summary():
    insight = ApprovedMeetingInsight(
        needs=["초음파 장비 교체"],
        purchase_barriers=["예산 승인 지연"],
        contact_signals=["구매팀 재문의"],
        next_meeting_agenda=["가격 재협상"],
    )
    result = _synthesize(_bundle(insight=insight))

    assert "초음파 장비 교체" in result.narrative
    assert "예산 승인 지연" in result.narrative
    assert result.customer_insight_summary == {
        "needs": ["초음파 장비 교체"],
        "purchase_barriers": ["예산 승인 지연"],
        "contact_signals": ["구매팀 재문의"],
        "next_meeting_agenda": ["가격 재협상"],
    }
    assert "approved_meeting_insight" in result.cited_evidence


def test_no_insight_means_no_customer_insight_summary():
    result = _synthesize(_bundle())
    assert result.customer_insight_summary is None
    assert "approved_meeting_insight" not in result.cited_evidence


def test_cited_evidence_lists_each_risk_kind():
    result = _synthesize(_bundle(risks=[_MEDIUM_RISK, _HIGH_RISK]))
    assert "risk:delivery" in result.cited_evidence
    assert "risk:expiry" in result.cited_evidence


# ---- 팩토리 ----


def _settings(**overrides) -> Settings:
    defaults = dict(app_env="test", session_secret="x" * 32)
    defaults.update(overrides)
    return Settings(**defaults)


def test_factory_returns_mock_by_default():
    synthesizer = get_contract_briefing_synthesizer(_settings())
    assert isinstance(synthesizer, MockContractBriefingSynthesizer)


def test_factory_rejects_anthropic_without_api_key():
    with pytest.raises(RuntimeError, match="anthropic_api_key"):
        get_contract_briefing_synthesizer(_settings(llm_provider="anthropic"))


def test_factory_anthropic_without_package_installed_fails_clearly():
    with pytest.raises(RuntimeError, match="anthropic 패키지"):
        get_contract_briefing_synthesizer(
            _settings(llm_provider="anthropic", anthropic_api_key="dummy-key")
        )


def test_anthropic_synthesizer_cannot_be_constructed_without_package():
    with pytest.raises(RuntimeError, match="anthropic 패키지"):
        AnthropicContractBriefingSynthesizer(api_key="dummy-key")
