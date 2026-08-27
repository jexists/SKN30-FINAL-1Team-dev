import pytest
from pydantic import ValidationError

from app.agents import meeting_analysis
from app.ml import deal_baseline

UNKNOWN_FEATURES = {name: "Unknown" for name in deal_baseline.FEATURE_NAMES}


def test_feature_contract_uses_unknown_instead_of_guessing():
    output = meeting_analysis.MeetingFeatureOutput(
        features=UNKNOWN_FEATURES,
    )
    assert output.features.model_dump() == UNKNOWN_FEATURES
    assert tuple(output.features.model_dump()) == deal_baseline.FEATURE_NAMES

    with pytest.raises(ValidationError):
        meeting_analysis.MeetingFeatureOutput(
            features={**UNKNOWN_FEATURES, "Authority": "Maybe"},
        )

    with pytest.raises(ValidationError):
        meeting_analysis.MeetingFeatureOutput(
            features={**UNKNOWN_FEATURES, "unexpected": "Yes"},
        )


def test_input_snapshot_rejects_empty_or_oversized_transcript():
    with pytest.raises(ValueError, match="transcript_required"):
        meeting_analysis.input_snapshot("  ")
    with pytest.raises(ValueError, match="transcript_too_long"):
        meeting_analysis.input_snapshot("가" * 50_001)


@pytest.mark.anyio
async def test_run_uses_structured_llm_output_as_model_input(monkeypatch):
    extracted = meeting_analysis.MeetingFeatureOutput(
        features=UNKNOWN_FEATURES,
    )
    captured = {}

    async def fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return extracted

    def fake_predict(features):
        assert features == UNKNOWN_FEATURES
        return deal_baseline.DealPrediction(
            label="watch",
            high_probability=0.31,
            model_version=deal_baseline.MODEL_VERSION,
        )

    monkeypatch.setattr(meeting_analysis, "generate_structured", fake_generate_structured)
    monkeypatch.setattr(deal_baseline, "predict", fake_predict)

    result = await meeting_analysis.run(
        meeting_analysis.input_snapshot("고객이 다음 주까지 수정 견적서를 요청했습니다.")
    )

    assert result.deal_assessment.features.model_dump() == UNKNOWN_FEATURES
    assert result.deal_assessment.label == "watch"
    assert result.deal_assessment.high_probability == 0.31
    assert result.deal_assessment.model_version == deal_baseline.MODEL_VERSION
    assert captured["instructions"] == meeting_analysis.SYSTEM_PROMPT
    assert captured["schema"] is meeting_analysis.MeetingFeatureOutput
    assert captured["schema_name"] == "meeting_features"
    assert "고객이 다음 주까지 수정 견적서를 요청했습니다." in captured["input_text"]
