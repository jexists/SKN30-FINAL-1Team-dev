"""검증된 Stacking 앙상블로 딜의 성사 확률을 계산한다."""

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from app.core.config import settings

MODEL_VERSION = "deal-stacking-lr-v1"
METADATA_FILENAME = f"{MODEL_VERSION}.json"
METADATA_SHA256 = "71a39c37ae2f2d63d86c5adf9af7863bf8b51d032e35d18712d0a750726a0d42"

FEATURE_NAMES = (
    "Authority",
    "Competitors",
    "Purch_dept",
    "Budgt_alloc",
    "Forml_tend",
    "RFP",
    "Posit_statm",
    "Source",
    "Client",
    "Scope",
    "Cross_sale",
    "Deal_type",
    "Needs_def",
)
CATEGORY_VALUES = {
    "Authority": ("High", "Low", "Mid", "Unknown"),
    "Competitors": ("No", "Unknown", "Yes"),
    "Purch_dept": ("No", "Unknown", "Yes"),
    "Budgt_alloc": ("No", "Unknown", "Yes"),
    "Forml_tend": ("No", "Unknown", "Yes"),
    "RFP": ("No", "Unknown", "Yes"),
    "Posit_statm": ("Neutral", "No", "Unknown", "Yes"),
    "Source": (
        "Direct mail",
        "Event",
        "Joint past",
        "Media",
        "Online form",
        "Other",
        "Referral",
        "Unknown",
    ),
    "Client": ("Current", "New", "Past", "Unknown"),
    "Scope": ("Clear", "Few questions", "Low", "Unknown"),
    "Cross_sale": ("No", "Unknown", "Yes"),
    "Deal_type": ("Consulting", "Maintenance", "Project", "Solution", "Unknown"),
    "Needs_def": ("Info gathering", "No", "Poor", "Unknown", "Yes"),
}
BASE_MODEL_ORDER = (
    "LogisticRegression",
    "MultinomialNB",
    "ExtraTrees",
    "CatBoost",
    "TabICL",
)

_PREDICT_LOCK = Lock()


class DealModelError(RuntimeError):
    """모델 로드 또는 추론에 실패했을 때 외부에 안전한 오류 코드만 전달한다."""


@dataclass(frozen=True)
class DealPrediction:
    label: Literal["high", "watch"]
    high_probability: float
    model_version: str


def _sha256(path: Path) -> str:
    """파일을 청크 단위로 읽어 SHA-256 해시를 반환한다."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_artifact_path(artifact_dir: Path, file_info: dict[str, Any]) -> Path:
    """안전한 파일명과 SHA-256이 확인된 산출물 경로를 반환한다."""
    filename = file_info["path"]
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise ValueError("artifact_path_invalid")

    path = artifact_dir / filename
    if _sha256(path) != file_info["sha256"]:
        raise ValueError("artifact_hash_mismatch")
    return path


def _validate_tabicl_artifact(tabicl: Any) -> None:
    """원본 학습 행 없이 CPU 표현 캐시만 담긴 TabICL 산출물인지 검증한다."""
    generator = tabicl.ensemble_generator_
    if (
        tabicl.device != "cpu"
        or tabicl.device_.type != "cpu"
        or tabicl.kv_cache != "repr"
        or tabicl.cache_mode_ != "repr"
        or tabicl.model_kv_cache_ is None
        or generator.X_ is not None
        or generator.y_ is not None
        or any(
            preprocessor.X_transformed_ is not None
            for preprocessor in generator.preprocessors_.values()
        )
    ):
        raise ValueError("tabicl_persistence_invalid")


def _category_contract(raw: object) -> dict[str, tuple[str, ...]]:
    """메타데이터의 범주 목록을 비교 가능한 튜플 계약으로 변환한다."""
    if not isinstance(raw, dict):
        raise ValueError("category_contract_invalid")
    return {name: tuple(values) for name, values in raw.items() if isinstance(values, list)}


def _frame(records: list[Mapping[str, str]]) -> Any:
    """입력 레코드를 학습 시점과 동일한 범주형 DataFrame으로 만든다."""
    import pandas as pd

    frame = pd.DataFrame(records, columns=FEATURE_NAMES)
    for name, categories in CATEGORY_VALUES.items():
        frame[name] = pd.Categorical(frame[name], categories=categories)
    return frame


def _won_probabilities(model: Any, inputs: Any) -> Any:
    """모델 출력에서 유효한 Won 클래스 확률만 추출한다."""
    import numpy as np

    won_index = list(model.classes_).index(1)
    probabilities = np.asarray(model.predict_proba(inputs), dtype=float)[:, won_index]
    if (
        not np.isfinite(probabilities).all()
        or not ((0 <= probabilities) & (probabilities <= 1)).all()
    ):
        raise ValueError("model_probability_invalid")
    return probabilities


def _stacked_probabilities(models: dict[str, Any], stacking_model: Any, frame: Any) -> Any:
    """고정 순서의 베이스 확률을 Stacking 메타모델에 전달한다."""
    import numpy as np

    base_probabilities = np.column_stack(
        [_won_probabilities(models[name], frame) for name in BASE_MODEL_ORDER]
    )
    return _won_probabilities(stacking_model, base_probabilities)


@lru_cache(maxsize=1)
def _load_models() -> tuple[dict[str, Any], Any, float]:
    """해시와 계약을 검증한 산출물을 최초 추론 시 한 번만 메모리에 올린다."""
    try:
        import joblib
        import numpy as np
        from tabicl import TabICLClassifier

        artifact_dir = settings.deal_model_dir
        metadata_path = artifact_dir / METADATA_FILENAME
        if _sha256(metadata_path) != METADATA_SHA256:
            raise ValueError("metadata_hash_mismatch")

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            metadata["schema_version"] != 1
            or metadata["model_version"] != MODEL_VERSION
            or metadata["selected_model"] != "Stacking_LR"
            or tuple(metadata["base_model_order"]) != BASE_MODEL_ORDER
            or tuple(metadata["model_feature_names"]) != FEATURE_NAMES
            or _category_contract(metadata["category_values"]) != CATEGORY_VALUES
            or metadata["target"] != {"Lost": 0, "Won": 1}
            or metadata["classification_threshold"] != 0.5
            or metadata["serialization_device"] != {"tabicl": "cpu"}
            or metadata["persistence"]
            != {"tabicl": {"training_data_included": False, "kv_cache": "repr"}}
        ):
            raise ValueError("metadata_contract_invalid")

        bundle_path = _verified_artifact_path(artifact_dir, metadata["files"]["models"])
        tabicl_path = _verified_artifact_path(artifact_dir, metadata["files"]["tabicl"])
        bundle = joblib.load(bundle_path)
        if (
            bundle["schema_version"] != 1
            or bundle["model_version"] != MODEL_VERSION
            or tuple(bundle["base_model_order"]) != BASE_MODEL_ORDER
            or tuple(bundle["model_feature_names"]) != FEATURE_NAMES
            or _category_contract(bundle["category_values"]) != CATEGORY_VALUES
            or bundle["classification_threshold"] != metadata["classification_threshold"]
            or set(bundle["base_models"]) != set(BASE_MODEL_ORDER[:-1])
        ):
            raise ValueError("model_contract_invalid")

        tabicl = TabICLClassifier.load(tabicl_path, device="cpu")
        _validate_tabicl_artifact(tabicl)
        models = {**bundle["base_models"], "TabICL": tabicl}
        stacking_model = bundle["stacking_model"]
        for model in (*models.values(), stacking_model):
            if 0 not in model.classes_ or 1 not in model.classes_:
                raise ValueError("model_classes_invalid")

        self_check = metadata["self_check"]
        actual = _stacked_probabilities(models, stacking_model, _frame(self_check["records"]))
        np.testing.assert_allclose(
            actual,
            np.asarray(self_check["won_probabilities"], dtype=float),
            rtol=self_check["rtol"],
            atol=self_check["atol"],
        )
        return models, stacking_model, metadata["classification_threshold"]
    except Exception as error:
        raise DealModelError("deal_model_unavailable") from error


def _normalized_features(features: Mapping[str, str]) -> dict[str, str]:
    """13개 특성의 이름과 허용 범주를 검증하고 빈 값을 Unknown으로 바꾼다."""
    if set(features) != set(FEATURE_NAMES):
        raise ValueError("deal_features_invalid")

    normalized: dict[str, str] = {}
    for name in FEATURE_NAMES:
        value = features[name]
        if not isinstance(value, str):
            raise ValueError("deal_features_invalid")
        value = value.strip() or "Unknown"
        if value not in CATEGORY_VALUES[name]:
            raise ValueError("deal_features_invalid")
        normalized[name] = value
    return normalized


def predict(features: Mapping[str, str]) -> DealPrediction:
    """13개 구조화 특성으로 딜의 성사 확률과 운영 라벨을 반환한다."""
    frame = _frame([_normalized_features(features)])
    try:
        with _PREDICT_LOCK:
            models, stacking_model, threshold = _load_models()
            high_probability = float(_stacked_probabilities(models, stacking_model, frame)[0])
    except DealModelError:
        raise
    except Exception as error:
        raise DealModelError("deal_model_prediction_failed") from error

    if not math.isfinite(high_probability):
        raise DealModelError("deal_model_prediction_failed")
    label: Literal["high", "watch"] = "high" if high_probability >= threshold else "watch"
    return DealPrediction(
        label=label,
        high_probability=high_probability,
        model_version=MODEL_VERSION,
    )
