from pathlib import Path

import numpy as np
import pytest

from app.ml import deal_baseline


class _Model:
    def __init__(self, classes, probabilities):
        self.classes_ = np.asarray(classes)
        self.probabilities = np.asarray(probabilities)
        self.columns = None
        self.inputs = None

    def predict_proba(self, frame):
        self.columns = tuple(frame.columns) if hasattr(frame, "columns") else None
        self.inputs = np.asarray(frame)
        return np.tile(self.probabilities, (len(frame), 1))


def test_stacking_uses_ordered_base_probabilities_and_threshold(monkeypatch):
    models = {
        "LogisticRegression": _Model([0, 1], [0.2, 0.8]),
        "MultinomialNB": _Model([1, 0], [0.7, 0.3]),
        "ExtraTrees": _Model([0, 1], [0.4, 0.6]),
        "CatBoost": _Model([0, 1], [0.5, 0.5]),
        "TabICL": _Model([0, 1], [0.9, 0.1]),
    }
    stacking = _Model([0, 1], [0.3, 0.7])
    monkeypatch.setattr(
        deal_baseline,
        "_load_models",
        lambda: (models, stacking, 0.5),
    )

    features = {name: "Unknown" for name in deal_baseline.FEATURE_NAMES}
    prediction = deal_baseline.predict(features)

    assert prediction.label == "high"
    assert prediction.high_probability == pytest.approx(0.7)
    assert prediction.model_version == "deal-stacking-lr-v1"
    assert all(model.columns == deal_baseline.FEATURE_NAMES for model in models.values())
    np.testing.assert_allclose(stacking.inputs, [[0.8, 0.7, 0.6, 0.5, 0.1]])

    with pytest.raises(ValueError, match="deal_features_invalid"):
        deal_baseline.predict({"Authority": "Unknown"})
    with pytest.raises(ValueError, match="deal_features_invalid"):
        deal_baseline.predict({**features, "Authority": "Maybe"})
    assert deal_baseline._normalized_features({**features, "Authority": " "})["Authority"] == (
        "Unknown"
    )


def test_artifact_path_must_be_local_and_match_hash(tmp_path: Path):
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"verified model")
    file_info = {
        "path": artifact.name,
        "sha256": deal_baseline._sha256(artifact),
    }

    assert deal_baseline._verified_artifact_path(tmp_path, file_info) == artifact

    with pytest.raises(ValueError, match="artifact_path_invalid"):
        deal_baseline._verified_artifact_path(
            tmp_path,
            {**file_info, "path": "../model.bin"},
        )
    with pytest.raises(ValueError, match="artifact_hash_mismatch"):
        deal_baseline._verified_artifact_path(
            tmp_path,
            {**file_info, "sha256": "0" * 64},
        )
