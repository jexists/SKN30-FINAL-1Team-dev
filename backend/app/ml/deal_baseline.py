"""검증된 Stacking 앙상블로 딜의 성사 확률을 계산한다."""

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from app.core.config import settings

MODEL_VERSION = "deal-paper-rf-ensemble-v1"
MODEL_FILENAME = f"{MODEL_VERSION}.joblib"
MODEL_SHA256 = "609c5d63b201fcb125cca9cddc2fcbe229f76d3ebf0a1417466d027248b17681"
# 고정된 합성 입력 3개의 기대값이다. 실제 고객 데이터나 성능 평가값이 아니다.
SELF_CHECK_WON_PROBABILITIES = (0.5625386746948857, 0.3512072797418429, 0.567269464941283)

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
    "RandomForest_tuned",
    "LogisticRegression",
    "ExtraTrees",
    "CatBoost",
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

    classes = list(model.classes_)
    if len(classes) != 2 or set(classes) != {0, 1}:
        raise ValueError("model_classes_invalid")
    probabilities = np.asarray(model.predict_proba(inputs), dtype=float)
    if (
        probabilities.shape != (len(inputs), 2)
        or not np.isfinite(probabilities).all()
        or not ((0 <= probabilities) & (probabilities <= 1)).all()
        or not np.allclose(probabilities.sum(axis=1), 1, rtol=1e-7, atol=1e-9)
    ):
        raise ValueError("model_probability_invalid")
    return probabilities[:, classes.index(1)]


@lru_cache(maxsize=1)
def _load_models() -> tuple[Any, float]:
    """해시와 계약을 검증한 산출물을 최초 추론 시 한 번만 메모리에 올린다."""
    try:
        import joblib
        import numpy as np

        # joblib은 역직렬화 중 코드를 실행할 수 있어 반드시 먼저 고정 해시를 검사한다.
        bundle_path = _verified_artifact_path(
            settings.deal_model_dir, {"path": MODEL_FILENAME, "sha256": MODEL_SHA256}
        )
        bundle = joblib.load(bundle_path)
        if (
            bundle["schema_version"] != 1
            or bundle["model_version"] != MODEL_VERSION
            or bundle["selected_candidate"] != "Stacking_LR"
            or tuple(bundle["model_feature_names"]) != FEATURE_NAMES
            or _category_contract(bundle["category_values"]) != CATEGORY_VALUES
            or bundle["target"] != {"Lost": 0, "Won": 1}
            or bundle["classification_threshold"] != 0.5
        ):
            raise ValueError("model_contract_invalid")

        model = bundle["model"]
        if (
            tuple(model.feature_names_in_) != FEATURE_NAMES
            or tuple(model.named_estimators_) != BASE_MODEL_ORDER
        ):
            raise ValueError("model_contract_invalid")
        for estimator in (model, *model.named_estimators_.values(), model.final_estimator_):
            if len(estimator.classes_) != 2 or set(estimator.classes_) != {0, 1}:
                raise ValueError("model_classes_invalid")

        # 학습 가중치는 그대로 쓰고 서버 내 병렬 작업 확산만 제한한다.
        model.n_jobs = 1
        known = {
            name: next(value for value in CATEGORY_VALUES[name] if value != "Unknown")
            for name in FEATURE_NAMES
        }
        records = [
            known,
            {**known, **dict.fromkeys(FEATURE_NAMES[:4], "Unknown")},
            dict.fromkeys(FEATURE_NAMES, "Unknown"),
        ]
        actual = _won_probabilities(model, _frame(records))
        np.testing.assert_allclose(
            actual,
            SELF_CHECK_WON_PROBABILITIES,
            rtol=1e-7,
            atol=1e-8,
        )
        return model, bundle["classification_threshold"]
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
            model, threshold = _load_models()
            high_probability = float(_won_probabilities(model, frame)[0])
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
