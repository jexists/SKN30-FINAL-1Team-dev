"""실제 모델로 교체하기 전 계약가능성 50:50 기준 분류기."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from sklearn.dummy import DummyClassifier

MODEL_VERSION = "deal-dummy-uniform-v0"

FEATURE_NAMES = (
    "Authority",
    "Competitors",
    "Purch_dept",
    "Budgt_alloc",
    "Forml_tend",
    "RFI",
    "RFP",
    "Posit_statm",
    "Scope",
    "Needs_def",
)

_classifier = DummyClassifier(strategy="uniform", random_state=42)
_classifier.fit(
    [["Unknown"] * len(FEATURE_NAMES), ["Unknown"] * len(FEATURE_NAMES)],
    ["high", "watch"],
)


@dataclass(frozen=True)
class DealPrediction:
    label: Literal["high", "watch"]
    high_probability: float
    model_version: str


def predict(features: Mapping[str, str]) -> DealPrediction:
    """입력은 무시하는 50:50 기준값을 반환한다."""
    if set(features) != set(FEATURE_NAMES):
        raise ValueError("deal_features_invalid")

    matrix = [[features[name] for name in FEATURE_NAMES]]
    probabilities = _classifier.predict_proba(matrix)[0]
    high_index = list(_classifier.classes_).index("high")
    high_probability = float(probabilities[high_index])

    # 근거 없는 동률을 '높음'으로 과장하지 않는다.
    label: Literal["high", "watch"] = "high" if high_probability > 0.5 else "watch"
    return DealPrediction(
        label=label,
        high_probability=high_probability,
        model_version=MODEL_VERSION,
    )
