from pathlib import Path

import joblib
import numpy as np
import pytest

from app.ml import deal_baseline


class _Model:
    def __init__(self, classes, probabilities):
        """테스트에 사용할 클래스 순서와 고정 확률을 저장한다."""
        self.classes_ = np.asarray(classes)
        self.probabilities = np.asarray(probabilities)
        self.columns = None
        self.inputs = None

    def predict_proba(self, frame):
        """입력 모양을 기록하고 행마다 고정 확률을 반환한다."""
        self.columns = tuple(frame.columns) if hasattr(frame, "columns") else None
        self.inputs = np.asarray(frame)
        return np.tile(self.probabilities, (len(frame), 1))


@pytest.fixture
def features():
    return {name: "Unknown" for name in deal_baseline.FEATURE_NAMES}


@pytest.mark.parametrize(
    ("classes", "probabilities", "label", "won_probability"),
    [
        ([0, 1], [0.3, 0.7], "high", 0.7),
        ([1, 0], [0.7, 0.3], "high", 0.7),
        ([0, 1], [0.5, 0.5], "high", 0.5),
        ([0, 1], [0.500001, 0.499999], "watch", 0.499999),
    ],
)
def test_predict_uses_single_stacking_model(
    monkeypatch, features, classes, probabilities, label, won_probability
):
    """완성된 Stacking 모델에 13개 입력을 전달하고 Won 확률에 임계값을 적용한다."""
    model = _Model(classes, probabilities)
    monkeypatch.setattr(deal_baseline, "_load_models", lambda: (model, 0.5))

    prediction = deal_baseline.predict(features)

    assert prediction.label == label
    assert prediction.high_probability == pytest.approx(won_probability)
    assert prediction.model_version == "deal-paper-rf-ensemble-v1"
    assert model.columns == deal_baseline.FEATURE_NAMES
    assert model.inputs.shape == (1, 13)
    assert (model.inputs == "Unknown").all()


@pytest.mark.parametrize("invalid", [None, 1, "Maybe"])
def test_invalid_category_is_rejected_before_model_load(monkeypatch, features, invalid):
    def unexpected_load():
        pytest.fail("invalid input must not load the model")

    monkeypatch.setattr(deal_baseline, "_load_models", unexpected_load)
    with pytest.raises(ValueError, match="^deal_features_invalid$"):
        deal_baseline.predict({**features, "Authority": invalid})


def test_feature_names_and_blank_normalization(features):
    """누락·추가 컬럼은 거부하고 공백은 Unknown으로 정규화한다."""
    for invalid in ({"Authority": "Unknown"}, {**features, "Product": "Unknown"}):
        with pytest.raises(ValueError, match="^deal_features_invalid$"):
            deal_baseline._normalized_features(invalid)
    normalized = deal_baseline._normalized_features(
        {**features, "Authority": " ", "Competitors": " Yes "}
    )
    assert normalized["Authority"] == "Unknown"
    assert normalized["Competitors"] == "Yes"


@pytest.mark.parametrize("probabilities", [[0.3, np.nan], [0.3, np.inf], [1.1, -0.1], [-0.1, 1.1]])
def test_invalid_probability_is_not_exposed(monkeypatch, features, probabilities):
    model = _Model([0, 1], probabilities)
    monkeypatch.setattr(deal_baseline, "_load_models", lambda: (model, 0.5))
    with pytest.raises(deal_baseline.DealModelError, match="^deal_model_prediction_failed$"):
        deal_baseline.predict(features)


def test_prediction_failure_does_not_expose_model_exception(monkeypatch, features):
    def broken_load():
        raise RuntimeError("customer-specific sensitive value")

    monkeypatch.setattr(deal_baseline, "_load_models", broken_load)
    with pytest.raises(deal_baseline.DealModelError) as error:
        deal_baseline.predict(features)
    assert str(error.value) == "deal_model_prediction_failed"


def test_load_failure_keeps_safe_error_code(monkeypatch, features):
    def unavailable():
        raise deal_baseline.DealModelError("deal_model_unavailable")

    monkeypatch.setattr(deal_baseline, "_load_models", unavailable)
    with pytest.raises(deal_baseline.DealModelError, match="^deal_model_unavailable$"):
        deal_baseline.predict(features)


def test_artifact_path_must_be_local_and_match_hash(tmp_path: Path):
    """산출물 경로 이탈과 해시 불일치가 거부되는지 검증한다."""
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


@pytest.fixture
def model_bundle(monkeypatch, tmp_path):
    """실제 학습 데이터 없이 해시 확인부터 셀프 체크까지 로더 경로를 실행한다."""
    model = _Model([0, 1], [0.3, 0.7])
    model.feature_names_in_ = np.asarray(deal_baseline.FEATURE_NAMES)
    model.named_estimators_ = {
        name: _Model([0, 1], [0.3, 0.7])
        for name in ("RandomForest_tuned", "LogisticRegression", "ExtraTrees", "CatBoost")
    }
    model.final_estimator_ = _Model([0, 1], [0.3, 0.7])
    model.n_jobs = 4
    ordinary_predict = model.predict_proba

    def predict_proba(frame):
        if len(frame) == 3:
            model.self_check_inputs = frame.copy()
            won = np.asarray(deal_baseline.SELF_CHECK_WON_PROBABILITIES)
            return np.column_stack((1 - won, won))
        return ordinary_predict(frame)

    model.predict_proba = predict_proba
    bundle = {
        "schema_version": 1,
        "model_version": "deal-paper-rf-ensemble-v1",
        "selected_candidate": "Stacking_LR",
        "model_feature_names": list(deal_baseline.FEATURE_NAMES),
        "category_values": {
            name: list(values) for name, values in deal_baseline.CATEGORY_VALUES.items()
        },
        "target": {"Lost": 0, "Won": 1},
        "classification_threshold": 0.5,
        "model": model,
    }
    artifact = tmp_path / deal_baseline.MODEL_FILENAME
    artifact.write_bytes(b"test artifact, never unpickled")
    monkeypatch.setattr(deal_baseline.settings, "deal_model_dir", tmp_path)
    monkeypatch.setattr(deal_baseline, "MODEL_SHA256", deal_baseline._sha256(artifact))
    loaded_paths = []

    def fake_load(path):
        loaded_paths.append(path)
        return bundle

    monkeypatch.setattr(joblib, "load", fake_load)
    deal_baseline._load_models.cache_clear()
    yield bundle, artifact, loaded_paths
    deal_baseline._load_models.cache_clear()


def test_verified_model_is_loaded_once_and_cached(model_bundle):
    bundle, artifact, loaded_paths = model_bundle
    model, threshold = deal_baseline._load_models()

    assert model is bundle["model"]
    assert threshold == 0.5
    assert model.n_jobs == 1
    assert tuple(model.self_check_inputs.columns) == deal_baseline.FEATURE_NAMES
    assert model.self_check_inputs.eq("Unknown").sum(axis=1).tolist() == [0, 4, 13]
    assert deal_baseline._load_models() == (model, threshold)
    assert loaded_paths == [artifact]


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("schema_version", 2),
        ("model_version", "another-model"),
        ("selected_candidate", "ExtraTrees"),
        ("model_feature_names", list(reversed(deal_baseline.FEATURE_NAMES))),
        ("category_values", {}),
        ("target", {"Lost": 1, "Won": 0}),
        ("classification_threshold", 0.6),
    ],
)
def test_model_bundle_contract_mismatch_is_rejected(model_bundle, field, invalid):
    bundle, _, _ = model_bundle
    bundle[field] = invalid
    with pytest.raises(deal_baseline.DealModelError, match="^deal_model_unavailable$"):
        deal_baseline._load_models()


@pytest.mark.parametrize("part", ["model", "base", "meta"])
def test_invalid_classes_in_any_estimator_are_rejected(model_bundle, part):
    bundle, _, _ = model_bundle
    model = bundle["model"]
    estimator = {
        "model": model,
        "base": model.named_estimators_["RandomForest_tuned"],
        "meta": model.final_estimator_,
    }[part]
    estimator.classes_ = np.asarray([0, 1, 2])
    with pytest.raises(deal_baseline.DealModelError, match="^deal_model_unavailable$"):
        deal_baseline._load_models()


@pytest.mark.parametrize("contract", ["features", "estimator_order"])
def test_fitted_model_input_contract_is_rejected(model_bundle, contract):
    bundle, _, _ = model_bundle
    model = bundle["model"]
    if contract == "features":
        model.feature_names_in_ = model.feature_names_in_[::-1]
    else:
        model.named_estimators_ = dict(reversed(list(model.named_estimators_.items())))
    with pytest.raises(deal_baseline.DealModelError, match="^deal_model_unavailable$"):
        deal_baseline._load_models()


@pytest.mark.parametrize("problem", ["missing", "hash_mismatch"])
def test_missing_or_modified_artifact_is_rejected_before_unpickling(model_bundle, problem):
    _, artifact, loaded_paths = model_bundle
    if problem == "missing":
        artifact.unlink()
    else:
        artifact.write_bytes(b"modified untrusted artifact")

    with pytest.raises(deal_baseline.DealModelError, match="^deal_model_unavailable$"):
        deal_baseline._load_models()
    assert loaded_paths == []


def test_model_self_check_failure_is_rejected(model_bundle):
    bundle, _, _ = model_bundle
    bundle["model"].predict_proba = _Model([0, 1], [0.8, 0.2]).predict_proba
    with pytest.raises(deal_baseline.DealModelError, match="^deal_model_unavailable$"):
        deal_baseline._load_models()


def test_unpickling_failure_does_not_expose_sensitive_details(monkeypatch, model_bundle):
    def broken_load(path):
        raise RuntimeError("private artifact path and credentials")

    monkeypatch.setattr(joblib, "load", broken_load)
    with pytest.raises(deal_baseline.DealModelError) as error:
        deal_baseline._load_models()
    assert str(error.value) == "deal_model_unavailable"


@pytest.mark.parametrize("output", [[[0.2, 0.2]], [[0.8, 0.1, 0.1]], [[1.0]], [], [0.3, 0.7]])
def test_malformed_probability_output_is_rejected(monkeypatch, features, output):
    model = _Model([0, 1], [0.3, 0.7])
    monkeypatch.setattr(model, "predict_proba", lambda frame: np.asarray(output))
    monkeypatch.setattr(deal_baseline, "_load_models", lambda: (model, 0.5))
    with pytest.raises(deal_baseline.DealModelError, match="^deal_model_prediction_failed$"):
        deal_baseline.predict(features)
