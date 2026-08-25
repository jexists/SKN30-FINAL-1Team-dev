# 학습한 ML/DL 모델 산출물

## 1. 모델 카드

| 항목 | 내용 |
|---|---|
| 모델명 | SalesLuv Deal Win Probability Model |
| 모델 버전 | `deal-soft-voting-lr-tabicl-v1` |
| 선택 모델 | `SoftVoting_LR_TabICL` |
| 모델 유형 | LogisticRegression + 사전학습 표형 모델 TabICL Soft Voting |
| 출력 | `P(Won)` |
| 운영 임계값 | 0.50 |
| 아티팩트 저장 시각 | 2026-08-25 05:19:46 UTC |
| 현재 상태 | 전체 데이터 재학습·로컬 저장·CPU 재로드 검증 완료, 서비스 배포 전 |
| 성능 근거 | [머신러닝/딥러닝 학습결과서](./머신러닝_딥러닝_학습결과서.md) |

### 1.1 목적

22개 범주형 딜 조건으로 계약 성사 클래스 `Won`의 확률을 계산한다. 확률은 영업 담당자의 판단을 돕는 참고 정보이며, 모델 단독으로 딜 상태나 계약 의사결정을 변경하지 않는다.

### 1.2 모델 구조

```text
                         ┌─ OneHotEncoder + LogisticRegression ─ P_lr(Won) ─┐
22개 범주형 입력 ────────┤                                                   ├─ 평균 ─ P(Won)
                         └─ TabICL ───────────────────────── P_tabicl(Won) ─┘

P(Won) = (P_lr(Won) + P_tabicl(Won)) / 2
분류 기준 = Won if P(Won) >= 0.50 else Lost
```

두 구성요소의 `Won=1` 확률을 동일 가중치로 평균한다. 새로운 컬럼을 만들거나 누락된 사실을 자동으로 채우는 모델 구조는 아니다.

### 1.3 구성요소

#### LogisticRegression

```text
Pipeline
├── OneHotEncoder(handle_unknown="ignore")
└── LogisticRegression(
      C=0.1,
      l1_ratio=0,
      max_iter=2000,
      random_state=1,
    )
```

#### TabICL

| 파라미터 | 값 |
|---|---|
| `checkpoint_version` | `tabicl-classifier-v2-20260212.ckpt` |
| `n_estimators` | 16 |
| `norm_methods` | `quantile` |
| `feat_shuffle_method` | `latin` |
| `average_logits` | `True` |
| `softmax_temperature` | 0.9 |
| `random_state` | 1 |

사용한 TabICL 2.1.1 구성은 TabICLv2 체크포인트를 사용하는 표형 사전학습 모델이다. 이번 `fit`은 사전학습 가중치를 미세조정하지 않고 365건을 추론 문맥으로 설정한다. 저장 파일에는 사전학습 모델 가중치와 전체 365건 문맥이 포함되고 KV cache는 포함하지 않는다.

## 2. 입력과 출력 계약

### 2.1 입력

입력은 아래 이름을 정확히 사용하는 22개 문자열 필드다. 추론 전에 누락·추가 필드와 결측값을 거부하고 이 순서로 정렬해야 한다.

| 순서 | 필드 | 의미 |
|---:|---|---|
| 1 | `Product` | 제안 상품 코드 |
| 2 | `Seller` | 영업 담당자 코드 |
| 3 | `Authority` | 고객 측 의사결정 권한 수준 |
| 4 | `Comp_size` | 고객사 규모 |
| 5 | `Competitors` | 경쟁사 존재 여부 |
| 6 | `Purch_dept` | 구매부서 참여 여부 |
| 7 | `Partnership` | 파트너 협업 판매 여부 |
| 8 | `Budgt_alloc` | 예산 확보 여부 |
| 9 | `Forml_tend` | 공식 입찰 여부 |
| 10 | `RFI` | 정보요청서 여부 |
| 11 | `RFP` | 제안요청서 여부 |
| 12 | `Growth` | 고객 성장 상태 |
| 13 | `Posit_statm` | 고객의 긍정 표현 |
| 14 | `Source` | 영업기회 유입 경로 |
| 15 | `Client` | 신규·기존·과거 고객 유형 |
| 16 | `Scope` | 수행 범위 명확성 |
| 17 | `Strat_deal` | 전략적 중요도 |
| 18 | `Cross_sale` | 교차판매 여부 |
| 19 | `Up_sale` | 상향판매 여부 |
| 20 | `Deal_type` | 거래 유형 |
| 21 | `Needs_def` | 요구사항 정의 수준 |
| 22 | `Att_t_client` | 고객 관리 유형 |

학습 과정에서는 원본에 기록된 `Unknown`만 범주로 사용했으며, 합성 `Unknown`이나 임의 결측값을 만들지 않았다. 서비스가 값을 확인할 수 없을 때 어떤 필드에 `Unknown`을 허용할지는 22개 구조화 Agent의 입력 계약에서 별도로 확정해야 한다.

### 2.2 출력

| 필드 | 형식 | 설명 |
|---|---|---|
| `won_probability` | 0~1 실수 | 두 구성요소가 계산한 Won 확률의 평균 |
| `predicted_class` | `Won` 또는 `Lost` | 0.50 임계값 적용 결과 |
| `model_version` | 문자열 | `deal-soft-voting-lr-tabicl-v1` |

현재 백엔드의 `high/watch` 응답 계약과 연결하는 코드는 아직 구현되지 않았다. 서비스 연결 시 `won_probability`와 0.50 임계값을 기존 UI 표현으로 매핑해야 한다.

## 3. 학습 데이터와 평가 정보

| 항목 | 값 |
|---|---|
| 출처 | Salvirt B2B Sales Dataset |
| 원본 SHA-256 | `8dee635b95bdcb00896b654efe62fc20177090081c81ef5224e8641ba31c3061` |
| 노트북 원본 위치 | `SALESLUV_B2B_DATA_PATH` 환경변수, 기본값 `/private/tmp/Salvirt_B2B_ML_dataset_HF.csv` |
| 원본 행 | 448 |
| 완전 동일 행 제거 후 | 365 |
| 정답 | `Lost=0`, `Won=1` |
| 평가 분할 | Train 255 / Test 110, 층화, `random_state=1` |
| 선택 기준 | Train 내부 5-Fold CV Brier |
| 최종 재학습 | 중복 제거된 전체 365건 |

| 지표 | Train 5-Fold OOF | Test |
|---|---:|---:|
| Brier | 0.160846 | 0.165947 |
| AUC | 0.841649 | 0.830736 |
| Accuracy, threshold 0.50 | 0.772549 | 0.790909 |

이 수치는 모델 선택용 Train 255건과 확인용 Test 110건에서 얻었다. 저장된 배포 모델은 그 이후 전체 365건으로 다시 학습했으므로, 위 수치를 저장 모델 자체에서 별도 측정한 값으로 해석하면 안 된다.

원본 CSV는 저장소에 포함하지 않는다. 재현 시 공식 배포처에서 직접 받아 위 경로에 배치하고 SHA-256을 확인한다.

## 4. 구성 파일

모델 아티팩트는 데이터 재배포 조건과 GitHub 파일 크기 제한을 고려해 PR에 포함하지 않고 검증된 로컬 사본으로 보관한다. 서비스 연결 시 다음 디렉터리에 별도로 주입한다.

```text
backend/pipeline/artifacts/
```

아래 명령은 아티팩트를 주입한 저장소 루트에서 실행한다.

| 파일 | 역할 | 크기 | SHA-256 |
|---|---|---:|---|
| `deal-soft-voting-lr-tabicl-v1-logistic.joblib` | OneHotEncoder+LogisticRegression | 2,555 bytes | `26ed53a2b885d92cbc61e41425d366ea7149ec9b52b63aaa0ad364dca4444d7d` |
| `deal-soft-voting-lr-tabicl-v1-tabicl.pkl` | TabICL 가중치와 학습 문맥 | 110,557,413 bytes | `e0e811dc08b2f0d2063283693afb95793a19364ffb186e44d93d668f8eef4cd3` |
| `deal-soft-voting-lr-tabicl-v1.json` | 모델·데이터·평가·환경 메타데이터 | 2,940 bytes | `fa3fd81264e61525a2565e1cad1fa89b00747893ed35b5ab4edcd774fd748e66` |

JSON 메타데이터는 다음 정보를 보관한다.

- 모델·스키마 버전
- 1:1 Soft Voting 구성과 임계값
- 22개 입력 순서와 정답 매핑
- 원본 데이터 SHA-256과 행 수
- 평가 분할과 성능
- 전체 365건 재학습 여부
- 구성 모델 파일의 크기와 SHA-256
- 실행환경 버전
- 재로드 확인용 16건의 기준 확률과 허용오차

## 5. 실행환경

학습과 재로드에 사용한 고정 버전은 다음과 같다.

| 패키지 | 버전 |
|---|---|
| Python | 3.13.13 |
| joblib | 1.5.3 |
| NumPy | 2.5.2 |
| pandas | 3.0.5 |
| scikit-learn | 1.9.0 |
| TabICL | 2.1.1 |
| PyTorch | 2.13.0 |

전용 환경 파일:

```text
backend/notebooks/pyproject.toml
backend/notebooks/uv.lock
```

저장소 루트에서 환경을 재현한다.

```bash
uv sync --project backend/notebooks --locked
```

현재 서비스용 `backend/pyproject.toml`과 `backend/uv.lock`에는 TabICL·PyTorch·pandas 런타임 구성이 반영되지 않았다. 서비스에서 모델을 사용하기 전에 배포 환경을 별도로 확정해야 한다.

## 6. 무결성 확인

모델을 로드하기 전에 파일 해시를 확인한다.

```bash
shasum -a 256 \
  backend/pipeline/artifacts/deal-soft-voting-lr-tabicl-v1-logistic.joblib \
  backend/pipeline/artifacts/deal-soft-voting-lr-tabicl-v1-tabicl.pkl \
  backend/pipeline/artifacts/deal-soft-voting-lr-tabicl-v1.json
```

기대 결과:

```text
26ed53a2b885d92cbc61e41425d366ea7149ec9b52b63aaa0ad364dca4444d7d  backend/pipeline/artifacts/deal-soft-voting-lr-tabicl-v1-logistic.joblib
e0e811dc08b2f0d2063283693afb95793a19364ffb186e44d93d668f8eef4cd3  backend/pipeline/artifacts/deal-soft-voting-lr-tabicl-v1-tabicl.pkl
fa3fd81264e61525a2565e1cad1fa89b00747893ed35b5ab4edcd774fd748e66  backend/pipeline/artifacts/deal-soft-voting-lr-tabicl-v1.json
```

joblib과 pickle 계열 파일은 로드 과정에서 코드를 실행할 수 있다. 사용자가 업로드한 파일이나 출처를 확인할 수 없는 파일을 로드하지 않고, 신뢰할 수 있는 릴리스에서 받은 파일과 해시만 사용한다.

## 7. 로드 및 추론 방법

아래 코드는 저장소 루트에서 아티팩트 디렉터리의 두 모델을 CPU로 불러와 `Won` 확률을 계산하는 최소 예다. 메타데이터를 신뢰할 수 있는 릴리스에서 받았다는 전제에서, 모델 파일의 SHA-256을 확인한 뒤 로드한다.

```python
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import joblib
import pandas as pd
from tabicl import TabICLClassifier

ARTIFACT_DIR = Path("backend/pipeline/artifacts").resolve()
METADATA_PATH = ARTIFACT_DIR / "deal-soft-voting-lr-tabicl-v1.json"
EXPECTED_METADATA_SHA256 = (
    "fa3fd81264e61525a2565e1cad1fa89b00747893ed35b5ab4edcd774fd748e66"
)
LOGISTIC_FILENAME = "deal-soft-voting-lr-tabicl-v1-logistic.joblib"
TABICL_FILENAME = "deal-soft-voting-lr-tabicl-v1-tabicl.pkl"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if sha256(METADATA_PATH) != EXPECTED_METADATA_SHA256:
    raise RuntimeError("model metadata SHA-256 mismatch")

metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
logistic_path = ARTIFACT_DIR / LOGISTIC_FILENAME
tabicl_path = ARTIFACT_DIR / TABICL_FILENAME

if sha256(logistic_path) != metadata["files"]["logistic"]["sha256"]:
    raise RuntimeError("LogisticRegression artifact SHA-256 mismatch")
if sha256(tabicl_path) != metadata["files"]["tabicl"]["sha256"]:
    raise RuntimeError("TabICL artifact SHA-256 mismatch")

logistic = joblib.load(logistic_path)
tabicl = TabICLClassifier.load(tabicl_path, device="cpu")


def predict(records: list[dict[str, str]]) -> list[dict[str, object]]:
    feature_names = metadata["feature_names"]
    expected = set(feature_names)

    if not records:
        raise ValueError("at least one record is required")

    normalized = []
    for record in records:
        if set(record) != expected:
            raise ValueError("input fields do not match the 22-feature schema")
        if any(
            not isinstance(record[name], str) or not record[name].strip()
            for name in feature_names
        ):
            raise ValueError("every feature must be a non-empty string")
        normalized.append({name: record[name].strip() for name in feature_names})

    frame = pd.DataFrame(normalized, columns=feature_names)
    logistic_won_index = list(logistic.classes_).index(1)
    tabicl_won_index = list(tabicl.classes_).index(1)

    logistic_probability = logistic.predict_proba(frame)[:, logistic_won_index]
    tabicl_probability = tabicl.predict_proba(frame)[:, tabicl_won_index]
    won_probability = (logistic_probability + tabicl_probability) / 2
    threshold = float(metadata["operating_threshold"])

    return [
        {
            "won_probability": float(probability),
            "predicted_class": "Won" if probability >= threshold else "Lost",
            "model_version": metadata["model_version"],
        }
        for probability in won_probability
    ]
```

호출자는 실제 허용 범주와 22개 필드 계약을 API 입력 경계에서 검증해야 한다. LogisticRegression의 `handle_unknown="ignore"`는 학습에서 보지 못한 값이 들어왔을 때 오류 대신 해당 특성의 one-hot 값을 모두 0으로 만들기 때문에, 입력 검증을 생략하는 근거가 되지 않는다.

## 8. 저장·재로드 검증 결과

보고서 작성 시 기존 노트북 프로세스와 분리된 새 오프라인 CPU 프로세스에서 다음 절차를 다시 수행했다.

1. 원본 CSV의 SHA-256을 확인했다.
2. 동일하게 문자열 공백 정리와 완전 중복 제거를 적용했다.
3. 두 아티팩트의 SHA-256을 JSON과 비교했다.
4. LogisticRegression과 TabICL을 CPU에서 새로 로드했다.
5. 메타데이터에 기록된 첫 16행의 `P(Won)`을 다시 계산했다.
6. 저장 전 기준 확률과 `rtol=1e-5`, `atol=1e-6`로 비교했다.

```text
검증 행 수: 16
최대 절대 확률 차이: 2.086162567138672e-07
아티팩트 해시: 일치
CPU 재로드·추론: 통과
```

검증은 저장 파일이 같은 입력에 사실상 같은 확률을 반환함을 확인한다. 실제 SalesLuv 환경의 정확도나 지연시간을 검증한 것은 아니다.

위 수치는 별도 CPU 검증 명령의 터미널 출력에서 확인했으며 전용 검증 로그 파일은 생성하지 않았다. JSON에는 기준 확률·허용오차와 `reloaded_ensemble_probabilities_match` 상태가 보존돼 있다.

섹션 7의 로드 코드를 실행한 같은 프로세스에서 아래 self-check를 실행할 수 있다.

```python
import numpy as np

DATA_PATH = Path(
    os.environ.get(
        "SALESLUV_B2B_DATA_PATH",
        "/private/tmp/Salvirt_B2B_ML_dataset_HF.csv",
    )
).expanduser()
if sha256(DATA_PATH) != metadata["data"]["source_sha256"]:
    raise RuntimeError("source CSV SHA-256 mismatch")

data = pd.read_csv(DATA_PATH, sep=";", encoding="utf-8-sig", dtype=str)
data = data.apply(lambda column: column.str.strip())
data = data.drop_duplicates().reset_index(drop=True)

row_indices = metadata["self_check"]["row_indices"]
feature_names = metadata["feature_names"]
records = data.loc[row_indices, feature_names].to_dict(orient="records")
actual = np.asarray(
    [result["won_probability"] for result in predict(records)],
    dtype=float,
)
expected = np.asarray(metadata["self_check"]["won_probabilities"], dtype=float)
rtol = float(metadata["self_check"]["rtol"])
atol = float(metadata["self_check"]["atol"])

if not np.allclose(actual, expected, rtol=rtol, atol=atol):
    raise RuntimeError("reloaded ensemble probabilities do not match")

print(f"rows={len(actual)}")
print(f"max_probability_difference={np.max(np.abs(actual - expected)):.18g}")
print("cpu_reload_prediction=pass")
```

## 9. 배포 상태

| 항목 | 상태 | 설명 |
|---|---|---|
| 최종 모델 파일 생성 | 완료 | 작업용 ML worktree에 로컬 저장 |
| 파일 해시 확인 | 완료 | JSON 값과 실측값 일치 |
| CPU 재로드·추론 | 완료 | 16건 확률 일치 |
| 서비스 저장소로 아티팩트 전달 | 미완료 | 현재 `backend/pipeline`에는 최종 파일이 없음 |
| 모델 로더 구현 | 미완료 | 별도 운영 로더·검증 스크립트 없음 |
| 기존 더미 모델 교체 | 미완료 | 서비스는 `deal-dummy-uniform-v0` 사용 중 |
| 구조화 Agent 입력 확장 | 미완료 | 현재 미팅 분석은 10개 특성만 생성 |
| 런타임 의존성 배포 | 미완료 | TabICL·PyTorch·pandas 미반영 |
| API End-to-end 검증 | 미완료 | 미팅 → 22개 특성 → 모델 → 응답 흐름 미연결 |

따라서 `모델 학습과 저장 완료`는 사실이지만 `제품 배포 완료`는 아니다.

## 10. 알려진 제한사항

- Salvirt 데이터와 실제 SalesLuv 영업 데이터의 분포 차이를 검증하지 않았다.
- 딜·고객·담당자 그룹 분할 또는 시간 순서 검증을 하지 않았다.
- 임계값 0.50은 금액 기반 비용함수의 최적값이 아니다.
- 22개 특성을 미팅 원문에서 추출하는 구조화 Agent가 아직 없다.
- TabICL 파일은 약 105.44 MiB이며 런타임 메모리와 CPU 지연시간 측정이 필요하다.
- TabICL 아티팩트에는 학습 문맥이 포함된다. 향후 실제 고객 데이터로 재학습하면 모델 파일도 민감 데이터로 취급해야 한다.
- joblib/pickle 아티팩트는 신뢰할 수 있는 경로에서만 로드해야 한다.
- 데이터와 TabICL 가중치의 재배포·상업 이용 조건은 배포 전에 다시 확인해야 한다.

## 11. 버전 변경 기준

다음 중 하나가 바뀌면 새 모델 버전을 발행한다.

- 학습 데이터 또는 중복 처리
- 입력 특성·허용 범주·순서
- 전처리 방식
- 구성 모델 또는 하이퍼파라미터
- Soft Voting 가중치
- 운영 임계값
- 직렬화 형식 또는 필수 런타임 버전

## 12. 근거 파일과 참고문헌

재현 파일과 아티팩트의 저장소 기준 경로는 다음과 같다.

```text
backend/notebooks/deal_model_phase1.ipynb
backend/notebooks/deal_model_phase2.ipynb
backend/notebooks/deal_model_phase3.ipynb
backend/notebooks/pyproject.toml
backend/notebooks/uv.lock
backend/pipeline/artifacts/deal-soft-voting-lr-tabicl-v1-logistic.joblib
backend/pipeline/artifacts/deal-soft-voting-lr-tabicl-v1-tabicl.pkl
backend/pipeline/artifacts/deal-soft-voting-lr-tabicl-v1.json
```

노트북은 `backend/notebooks/`, 별도 배포되는 아티팩트는 `backend/pipeline/artifacts/`에서 관리한다.

- [TabICL 공식 구현](https://github.com/soda-inria/tabicl)
- [TabICLv2 논문](https://arxiv.org/abs/2602.11139)
- [scikit-learn 모델 저장 지침](https://scikit-learn.org/stable/model_persistence.html)
- [scikit-learn OneHotEncoder](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.OneHotEncoder.html)
- [Salvirt B2B Sales Dataset](https://www.salvirt.com/research/b2bdataset/)
