import pytest

from app.ml import deal_baseline


def test_uniform_baseline_returns_neutral_probability_and_safe_tie_label():
    prediction = deal_baseline.predict({name: "Unknown" for name in deal_baseline.FEATURE_NAMES})

    assert prediction.label == "watch"
    assert prediction.high_probability == 0.5
    assert prediction.model_version == "deal-dummy-uniform-v0"

    with pytest.raises(ValueError, match="deal_features_invalid"):
        deal_baseline.predict({"Authority": "Unknown"})
