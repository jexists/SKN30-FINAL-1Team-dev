# 학습한 ML/DL 모델 산출물

| 항목 | 내용 |
|---|---|
| 제품·역할 | SalesLuv B2B 딜의 `Won` 확률 및 승패 예측 |
| 선정 모델 | `Stacking_LR` |
| 모델 버전 | `deal-paper-rf-ensemble-v1` |
| 모델 유형 | RF·LR·ExtraTrees·CatBoost + LogisticRegression 메타모델 |
| 입력·임계값 | 13개 범주형 컬럼, `0.50` |
| 작성 기준일 | 2026-08-31 |
| 저장 모델 학습 범위 | 1회차 Train 원본 357건 × 마스킹 10세트 = 3,570행; Test 원본 91건은 학습에서 제외 |

## 1. 모델 카드

### 1.1 목적과 출력

구조화 Agent가 업무 보고서에서 추출한 13개 범주형 값을 받아 `Won` 확률을 계산하는 이진 분류 모델이다. 논문에서 선정한 RandomForest를 베이스라인 모델 계열로 삼았다. 논문의 학습 완료 파일과 세부 파라미터·튜닝 탐색 방법은 확인되지 않아, 공개된 8:2 분할·30회 반복 평가 방식을 참고해 RF를 직접 학습하고 우리 실험의 기준선으로 삼았다. 이후 우리가 추가한 GridSearch 튜닝과 앙상블 비교로 발전시켰다.

| 출력 해석 | 형식 | 의미 |
|---|---|---|
| 성사 확률 | 0~1 실수 | 모델의 `P(Won)` |
| 승패 분류 | `Won` / `Lost` | 확률이 `0.50` 이상이면 `Won` |
| 모델 버전 | 문자열 | `deal-paper-rf-ensemble-v1` |

모델은 영업 판단을 지원하며 계약 승인·딜 상태 변경·담당자 평가를 자동으로 결정하지 않는다.

### 1.2 구성과 선정 이유

| 기본 모델 | 사용 이유 | 모델 내부 입력 처리 |
|---|---|---|
| RandomForest | 논문의 RF를 출발점으로 삼아 같은 조건에서 튜닝 효과 비교 | 고정 범주 원핫 인코딩 |
| LogisticRegression | 작은 데이터에서 규제 가능한 단순 선형 기준 제공 | 고정 범주 원핫 인코딩 |
| ExtraTrees | 무작위 분할 트리로 RF와 다른 예측 특성 제공 | 고정 범주 원핫 인코딩 |
| CatBoost | 범주형을 직접 처리하는 부스팅 계열 결합 | 원본 범주형 13개 직접 입력 |

네 모델의 `P(Won)`을 순서대로 모아 LogisticRegression 메타모델에 넣는다. 메타모델에는 원본 입력을 추가하지 않는다(`passthrough=False`). 같은 원본 입력 그룹이 겹치지 않는 3-Fold OOF 확률로 결합 방법을 학습했다. 추론에는 저장된 `StackingClassifier.predict_proba()`를 사용한다.

모델 수를 늘리는 것 자체가 목적은 아니었다. 단일 모델 4종, 3개·4개 모델의 Soft Voting, 4개 모델의 Stacking을 동일 조건에서 비교하고 **예측 성능과 FP를 함께 고려해 기본 모델 4개 + LR 메타모델 1개의 구성을 선정했다.** 튜닝 RF보다 평균 Brier·Accuracy·AUC·FP·FPR이 나빠지지 않는 개선 후보 중 Brier가 가장 낮았기 때문이다. 다만 기본 모델을 하나씩 제외한 Stacking 비교는 수행하지 않았으므로, 4개가 반드시 필요한 최소 구성이라고 주장하지 않는다.

OOF는 기본 모델의 학습 행과 메타모델 학습용 확률을 만드는 행을 나누는 절차다. 기본 모델 파라미터는 해당 바깥 Train 전체의 내부 CV로 선택했으므로, OOF 자체를 파라미터 탐색까지 완전히 분리한 평가 점수로 보고하지 않는다.

## 2. 입력 명세

### 2.1 필드 의미와 허용 범주

| 필드 | 의미 | 허용 범주 |
|---|---|---|
| `Authority` | 고객 의사결정권자의 권한 수준 | High, Low, Mid, Unknown |
| `Competitors` | 경쟁사 존재·검토 여부 | No, Unknown, Yes |
| `Purch_dept` | 고객사 구매부서 참여 여부 | No, Unknown, Yes |
| `Budgt_alloc` | 고객 예산 확보·배정 여부 | No, Unknown, Yes |
| `Forml_tend` | 공식 입찰 절차 여부 | No, Unknown, Yes |
| `RFP` | 제안요청서 진행 여부 | No, Unknown, Yes |
| `Posit_statm` | 고객의 명시적 구매 표현 | Neutral, No, Unknown, Yes |
| `Source` | 영업기회 유입 경로 | Direct mail, Event, Joint past, Media, Online form, Other, Referral, Unknown |
| `Client` | 고객과의 거래 관계 | Current, New, Past, Unknown |
| `Scope` | 계약·수행 범위의 명확성 | Clear, Few questions, Low, Unknown |
| `Cross_sale` | 기존 고객 대상 교차판매 여부 | No, Unknown, Yes |
| `Deal_type` | 거래 유형 | Consulting, Maintenance, Project, Solution, Unknown |
| `Needs_def` | 고객 요구사항의 정의 수준 | Info gathering, No, Poor, Unknown, Yes |

### 2.2 전처리와 판정

1. 앞뒤 공백을 정리하고 측정되지 않은 값은 문자열 `Unknown`으로 통일한다. 미확인을 `No`로 바꾸지 않는다.
2. 저장된 `model_feature_names` 순서로 13개 필드를 구성한다. 허용 범주 밖의 문자열·오탈자는 입력 오류로 처리한다.
3. RF·LR·ExtraTrees의 Pipeline은 고정 범주와 `drop="first"`로 39개 숫자 컬럼을 만든다. CatBoost에는 13개 문자열 컬럼을 그대로 전달한다.
4. `classes_`에서 `1`의 확률 열을 찾아 `P(Won) >= 0.50`으로 판정한다. 정확히 0.50일 때도 평가 코드와 같은 결과가 되게 한다.

학습·평가 시 행마다 4개를 `Unknown`으로 둔 이유는 **실제 서비스에서 13개 입력 항목 중 약 30%가 누락될 것으로 예상했기 때문**이다. 서비스 설계 단계의 예상 결측률을 반영해 `13 × 30% = 3.9`를 반올림한 4개를 적용했으며, 기존 `Unknown`을 포함한 최종 개수를 4개로 맞췄다. 이 30%는 실제 사용자 데이터에서 측정한 수치가 아니다.

**실제 추론에서는 임의로 네 컬럼을 가리지 않는다.** 네 개 Unknown 마스킹은 학습·평가 실험용이다. 실제 입력에는 구조화 Agent가 확인하지 못한 항목만 Unknown으로 전달한다.

## 3. 학습 범위와 저장된 파라미터

원본 448건과 13개 입력을 유지했다. 같은 원본 입력 198개 그룹을 Train 158그룹 / Test 40그룹으로 나누는 30회 반복 평가를 수행했다. 그룹을 약 8:2로 나누므로 실제 행 수는 회차마다 다르다. 모든 후보에 같은 분할과 같은 10개 마스킹 세트를 적용했다.

RF는 각 바깥 Train에서 64개 조합을 5-Fold 그룹 CV로 탐색했다. 추가 모델도 같은 바깥 Train 내부에서 LR 8개, ExtraTrees 18개, CatBoost 18개 조합을 탐색했다. 파라미터 선택 기준은 `neg_brier_score`다. 임계값과 Soft Voting의 동일 가중치는 별도 튜닝하지 않았다.

최종 모델은 성능이 가장 높은 회차가 아니라 **미리 정한 1회차 Train**으로 학습했다. 원본 357건의 10개 마스킹 버전인 3,570행을 사용했고 나머지 91건은 학습에서 제외했다. 저장 모델의 평가는 분리된 Test 91건의 마스킹 10세트를 사용했다.

| 저장 객체 | 1회차 Train에서 선택한 주요 파라미터 |
|---|---|
| RandomForest | `n_estimators=300`, `max_depth=12`, `min_samples_leaf=5`, `max_features="sqrt"` |
| LogisticRegression | `C=0.1`, `class_weight=None`, `max_iter=3000`, `solver="lbfgs"` |
| ExtraTrees | `n_estimators=300`, `max_depth=12`, `min_samples_leaf=6`, `max_features="sqrt"` |
| CatBoost | `iterations=200`, `depth=4`, `learning_rate=0.05`, `l2_leaf_reg=3` |
| 메타모델 | `LogisticRegression(C=0.1, max_iter=3000, solver="lbfgs")` |

각 바깥 Train마다 최적 파라미터를 다시 선택했다. 위 한 세트의 파라미터로 30회 전체 성능을 얻었다고 해석하면 안 된다. 재현 난수는 `1`이며 RF·ExtraTrees·CatBoost는 CPU로 실행했다.

## 4. 성능 근거와 선택 해석

논문 RF의 Accuracy는 78.2%, AUC는 0.85였다. 이 값을 우리가 재현한 결과로 쓰지 않고, 같은 13개 입력·마스킹·그룹 분리 조건에서 직접 학습한 RF 성적을 개선의 출발점으로 사용했다.

| 발전 단계 | Accuracy ↑ | AUC ↑ | Brier ↓ |
|---|---:|---:|---:|
| 자체 학습 RF 베이스라인 | 0.695847 | 0.740949 | 0.209706 |
| RF 하이퍼파라미터 튜닝 | 0.733833 | 0.775560 | 0.190198 |
| 최종 선정 Stacking | 0.735980 | 0.778318 | 0.187965 |

최종 모델은 자체 베이스라인보다 Accuracy **4.01%p**, AUC **0.037369**가 개선됐고 Brier는 **0.021741** 낮아졌다. 이는 우리 조건 안의 개선이며, 입력과 평가 조건이 다른 논문보다 우수하다는 뜻은 아니다.

다음 표는 최종 모델 학습·평가 절차의 반복 평균과 실제 저장한 1회차 학습본을 구분한다.

| 지표 | Stacking 30회 평가 평균 | 저장 모델의 1회차 Test 평균 |
|---|---:|---:|
| Brier ↓ | 0.187965 | 0.206093 |
| ROC-AUC ↑ | 0.778318 | 0.732313 |
| Accuracy ↑ | 0.735980 | 0.716484 |
| Precision ↑ | 0.711869 | 0.714017 |
| Recall ↑ | 0.825865 | 0.789796 |
| F1 ↑ | 0.762654 | 0.749823 |
| FP / FN | 16.15 / 8.09 | 15.5 / 10.3 |
| FPR ↓ | 0.370101 | 0.369048 |

매 회차 Test의 10개 결측 패턴을 먼저 평균하고 그 값을 30회 평균했다. 10세트는 같은 거래를 공유하고 30회 분할도 서로 겹친다. 독립적인 새 거래 300세트나 독립된 최종 검증으로 해석하지 않는다. FP/FN은 평균 건수이므로 소수이며, 회차별 Test 규모 차이를 보완하려고 `FPR=FP/(FP+TN)`도 함께 본다.

Brier는 예측 확률의 제곱오차다. 실제 Lost인 거래를 높은 확률의 Won으로 확신할수록 불이익을 준다. 분류 문제라도 화면에 승률을 표시하므로 사용했다. 낮은 Brier만으로 확률 보정이 완벽하다고 보장할 수 없고, 모든 모델의 내부 학습 손실을 Brier로 바꾼 것도 아니다.

앙상블은 튜닝 RF보다 평균 Brier·Accuracy·AUC·FP·FPR 중 어느 것도 나빠지지 않고 한 항목 이상 좋아진 후보 중 최소 Brier를 선택했다. Stacking은 튜닝 RF 대비 Accuracy 0.21%p, AUC 0.002758이 개선됐고, Brier 0.002233 및 평균 FP 0.62건이 감소했다. 대신 FN은 0.45건 증가했다. CatBoost가 Accuracy 1위, 4개 모델 Soft Voting이 AUC 1위이므로 Stacking이 모든 지표에서 최고라는 뜻은 아니다.

FP는 실제로 주의가 필요한 Lost 거래를 쉽게 성사될 거래로 잘못 표시하는 오류다. 위험 신호·개입 시점을 놓치고 영업 우선순위와 예상 매출을 낙관적으로 판단할 수 있어 중요하게 봤다. 다만 Stacking의 FP 16.15는 튜닝 RF 16.77보다 낮을 뿐, 튜닝 전 RF 15.59보다 낮지는 않다. 임계값을 높여 FP만 줄이는 실험은 이번 선정에 사용하지 않았다.

논문은 22개 입력, 본 실험은 13개 입력·추가 결측·동일 입력 그룹 분리 조건이므로 직접적인 우열 비교가 아니다. 비교 결과를 보고 모델 계열을 선택했으므로 성능은 **탐색적 비교 결과**다. 작은 차이의 통계적 우위나 실제 고객 환경의 성능을 확정한 것은 아니다. 전체 비교와 평가 조건은 [학습결과서](머신러닝_딥러닝_학습결과서.md)에 기록했다.

## 5. 최종 모델 파일 명세

최종 산출물은 다음 단일 모델 파일이다.

```text
backend/pipeline/artifacts/deal-paper-rf-ensemble-v1.joblib
```

크기는 **17,139,030 bytes (16.345 MiB)**이며 SHA-256은 다음과 같다.

```text
609c5d63b201fcb125cca9cddc2fcbe229f76d3ebf0a1417466d027248b17681
```

파일에는 학습한 `model`, 13개 입력 스키마, 허용 범주, 임계값, 1회차 Train/Test 위치, 선택 파라미터, 30회 평가 결과, 패키지 버전이 함께 들어 있다. 인코딩 파이프라인과 구성 모델이 포함되어 별도 모델 파일 없이 추론한다.

## 6. 학습 환경

학습 환경은 Python 3.13.13, scikit-learn 1.9.0, numpy 2.5.2, pandas 3.0.5, CatBoost 1.2.10, joblib 1.5.3이다.

학습 데이터는 [Salvirt B2B Sales Dataset](https://www.salvirt.com/research/b2bdataset)의 [Hugging Face 배포본](https://huggingface.co/datasets/markobo/B2B_Sales_data/resolve/c3bae20f010d8ec74f6e9f85ef19368811dd15d3/Salvirt_B2B_ML_dataset_HF.csv)이다. 데이터 구성은 [학습결과서](머신러닝_딥러닝_학습결과서.md), 출처와 라이선스 표기는 [데이터 수집 보고서](../데이터%20수집%20보고서.md#33-외부-학습-데이터)에 정리했다.

## 7. 결론

최종 산출물은 13개 범주형 영업 정보를 입력받아 RF·LR·ExtraTrees·CatBoost의 예측을 LR 메타모델로 결합하는 `deal-paper-rf-ensemble-v1`이다. 동일한 평가 조건에서 RF 기준선 대비 평균 Accuracy·AUC·Brier가 개선됐으며, 반복 평가 평균과 저장 모델의 개별 성적을 구분해 예측 품질과 적용 범위를 제시했다.

향후 실제 사용자 미팅 데이터와 거래 승패가 축적되면 실제 결측률·누락 패턴을 바탕으로 마스킹 방식과 전처리를 조정하고 모델 하이퍼파라미터를 튜닝할 예정이다. 초기의 30% 결측 가정을 실제 서비스 데이터에 맞게 구체화하는 방향이다.
