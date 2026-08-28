# 학습한 ML/DL 모델 산출물

| 항목 | 내용 |
|---|---|
| 제품 | SalesLuv |
| 모델 역할 | B2B 딜의 `Won` 확률 및 승패 예측 |
| 최종 모델 | `Stacking_LR` |
| 모델 버전 | `deal-stacking-lr-v1` |
| 모델 유형 | 5개 기본 분류기 + LogisticRegression 메타모델 |
| 입력 | 13개 범주형 컬럼 |
| 분류 임계값 | `0.50` |
| 작성 기준일 | 2026-08-27 |
| 산출물 상태 | 기존 예측을 유지하며 TabICL을 CPU 이식 가능하게 재패키징, 배포 전 |

## 1. 모델 카드

### 1.1 목적과 출력

구조화 Agent가 업무 보고서에서 추출한 13개 범주형 값을 받아 계약 성사 클래스 `Won`의 확률을 계산한다.

| 출력 | 형식 | 설명 |
|---|---|---|
| `won_probability` | 0~1 실수 | Stacking 메타모델의 `P(Won)` |
| `predicted_class` | `Won` / `Lost` | `won_probability >= 0.50`이면 `Won` |
| `model_version` | 문자열 | `deal-stacking-lr-v1` |

모델 확률은 영업 판단을 지원하는 참고 정보다. 계약 승인, 딜 상태 변경, 담당자 평가는 서비스 운영 규칙과 사람이 결정한다.

### 1.2 구조

```text
13개 범주형 입력
├─ OneHotEncoder → LogisticRegression ─┐
├─ OneHotEncoder → MultinomialNB ──────┤
├─ OneHotEncoder → ExtraTrees ─────────┼─ 5개 P(Won)
├─ CatBoost ────────────────────────────┤
└─ TabICL ──────────────────────────────┘
                      ↓
        LogisticRegression 메타모델
                      ↓
              최종 P(Won), 임계값 0.50
```

Stacking 메타모델은 기본 모델의 OOF 확률로 학습한다. 최종 추론에는 다섯 기본 모델이 모두 필요하다.

다섯 기본 모델은 선형 확률 모델(LogisticRegression), 빈도 기반 확률 모델(MultinomialNB), 비선형 배깅 트리(ExtraTrees), 범주형 부스팅(CatBoost), 표형 파운데이션 모델(TabICL)을 각각 대표한다. 서로 다른 학습 방식의 확률을 비교하고 결합하기 위해 이 구성을 선택했다.

## 2. 입력 계약

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

### 2.2 검증 규칙

| 검증 항목 | 규칙 |
|---|---|
| 필드 | 요청은 13개 필드를 모두 포함한다. |
| 결측 | 측정되지 않은 값과 빈값은 구조화 단계에서 문자열 `Unknown`으로 변환한다. |
| 범주 | 허용 목록에 없는 범주는 입력 오류로 처리한다. |
| 스키마 | 컬럼 이름과 순서를 저장된 모델 스키마와 대조한다. |
| 정답 | 학습 정답은 `Lost=0`, `Won=1`로 매핑한다. |

## 3. 전처리 계약과 최적 파라미터

모델 입력은 다음 순서로 정규화한다.

1. 문자열 앞뒤 공백을 제거한다. 의미가 있는 값은 임의로 바꾸지 않는다.
2. 빈값과 측정되지 않은 값은 `No`가 아닌 문자열 `Unknown`으로 변환한다.
3. 13개 필드의 존재 여부, 순서, 허용 범주를 저장된 스키마와 대조한다.
4. LogisticRegression, MultinomialNB, ExtraTrees는 고정 범주 One-Hot Encoder로 39개 컬럼을 만든다.
5. CatBoost와 TabICL은 범주 정보를 보존하기 위해 원본 13개 범주형 컬럼을 직접 사용한다.

학습 단계의 30% 마스킹은 값 누락에 대한 강건성을 확보하기 위한 데이터 증강이다. 실제 추론에서는 구조화 Agent가 확인하지 못한 필드만 `Unknown`으로 전달하며, 임의로 네 개를 다시 마스킹하지 않는다.

| 모델 | 선택 파라미터 |
|---|---|
| LogisticRegression | `C=0.03`, `class_weight="balanced"` |
| MultinomialNB | `alpha=75.0`, `fit_prior=False` |
| ExtraTrees | `n_estimators=300`, `max_depth=8`, `max_features="sqrt"`, `min_samples_leaf=6` |
| CatBoost | `iterations=200`, `depth=4`, `learning_rate=0.01`, `l2_leaf_reg=7.0`, `random_strength=0.5` |
| TabICL | `n_estimators=8`, `norm_methods="quantile"`, `feat_shuffle_method="latin"`, `average_logits=True`, `softmax_temperature=1.1` |
| Stacking meta | `LogisticRegression(C=0.1, max_iter=3000, solver="lbfgs")` |

## 4. 학습 데이터와 성능 근거

| 항목 | 값 |
|---|---|
| 데이터 출처 | Salvirt B2B Sales Dataset, 실제 익명화 B2B 영업기회 |
| 원본 파일 SHA-256 | `8dee635b95bdcb00896b654efe62fc20177090081c81ef5224e8641ba31c3061` |
| 원본 | 448건, Lost 221 / Won 227 |
| 평가 분할 | Train 313건 / Test 135건, 입력 그룹 분리 |
| 마스킹 | 행마다 13개 중 4개 `Unknown`, 서로 다른 10세트 |
| 최종 재학습 | 전체 448건 × 10세트 = 4,480행 |
| 최종 재학습 그룹 | 198개 |

| 지표 | 반복 Group CV | Test 10세트 평균 |
|---|---:|---:|
| Brier ↓ | 0.194406 ± 0.001928 | 0.179131 ± 0.005902 |
| ROC-AUC ↑ | 0.766326 | 0.817164 |
| Accuracy ↑ | 0.720873 | 0.734074 |
| Precision ↑ | 0.695164 | 0.720534 |
| Recall ↑ | 0.802935 | 0.772059 |
| F1 ↑ | 0.745072 | 0.745083 |
| FP / FN | 56.03 / 31.33 | 20.4 / 15.5 |

보고 성능은 4단계의 분리 평가 결과다. 저장된 배포 모델은 모델 선택 이후 전체 448건으로 다시 학습했다.

모델과 하이퍼파라미터는 `Won` 확률의 정확성을 평가하는 Brier Score를 기준으로 선택했다. ROC-AUC와 Accuracy·F1은 보조 지표로 확인했고, FP/FN은 분류 임계값 적용 후의 업무 위험을 확인하는 지표로 사용했다. 특히 FP가 발생하면 실제로는 추가 관리가 필요한 `Lost` 위험 거래가 쉽게 성사될 거래처럼 표시된다. 이로 인해 위험 신호와 개입 시점을 놓치고 파이프라인과 예상 매출을 실제보다 낙관적으로 평가할 수 있다. 현재 모델의 임계값은 `0.50`으로 확정했으며, FP/FN은 운영 모니터링 지표로 기록한다.

## 5. 배포 아티팩트

저장 위치:

```text
backend/pipeline/artifacts/
```

| 파일 | 역할 | 크기 | SHA-256 |
|---|---|---:|---|
| `deal-stacking-lr-v1-models.joblib` | LR·NB·ExtraTrees·CatBoost·Stacking 메타모델·입력 스키마 | 1,316,965 bytes | `78a56a3bcc6a69da94fde8366c228036103f5c42b48d668fec2d1051cdbd4a6f` |
| `deal-stacking-lr-v1-tabicl.pkl` | CPU 직렬화한 TabICL 가중치와 표현 캐시(원본 학습 행 제외) | 237,348,751 bytes | `4d6de1c7724cb004b7901a7523e727061f7e9a944e7419114291fb859870f45c` |
| `deal-stacking-lr-v1.json` | 모델·스키마·평가·환경·해시·합성 기준 입력 확률 메타데이터 | 11,273 bytes | `71a39c37ae2f2d63d86c5adf9af7863bf8b51d032e35d18712d0a750726a0d42` |

joblib과 pickle 계열 파일은 로드 과정에서 코드를 실행할 수 있다. 신뢰할 수 있는 릴리스의 파일만 사용하고 로드 전에 SHA-256을 확인한다.

## 6. 저장·재로드 검증

| 검증 항목 | 결과 |
|---|---|
| 현재 프로세스 재로드 | 통과 |
| 현재 프로세스 최대 확률 차이 | `0` |
| 교체 전후 최대 확률 차이 | `2.850419115185687e-07` |
| 저장된 TabICL 장치 | `cpu` |
| TabICL 원본 학습 행 포함 | 없음 (`repr` 캐시 사용) |
| 기존 기준 확률 대비 최대 차이 | `1.3301953558642055e-06` |
| 초기 파일 Linux amd64 CPU 컨테이너 | MPS 오류 재현 |
| CPU 직렬화 파일 Linux amd64 CPU 컨테이너 | 통과 (`torch 2.13.0+cpu`, CUDA/MPS 비활성) |
| 허용오차 | `rtol=1e-5`, `atol=1e-6` |
| 모델 파일 SHA-256 | 메타데이터와 일치 |

재로드 검사는 메타데이터에 저장된 범주형 기준 입력 16건으로 수행했다. Linux 검사는 운영과 같은 백엔드 Dockerfile로 이미지를 빌드하고 실제 `_load_models()`와 `predict()`를 호출했다.

## 7. 재현 환경과 파일

| 패키지 | 버전 |
|---|---|
| Python | 3.13.13 |
| pandas | 3.0.5 |
| scikit-learn | 1.9.0 |
| CatBoost | 1.2.10 |
| TabICL | 2.1.1 |
| PyTorch | 2.13.0 |
| joblib | 1.5.3 |

```text
backend/notebooks/deal_data_preprocessing.ipynb
backend/notebooks/deal_model_phase2.ipynb
backend/notebooks/deal_model_phase3.ipynb
backend/notebooks/deal_model_phase4.ipynb
backend/notebooks/deal_model_phase5_threshold.ipynb
backend/notebooks/deal_model_finalization.ipynb
backend/notebooks/pyproject.toml
backend/notebooks/uv.lock
```

TabICL 최종 학습에는 MPS를 사용했다. 배포 파일은 학습 결과를 바꾸지 않고 직렬화 장치만 CPU로 고정해 Linux CPU 환경에서도 MPS를 먼저 찾지 않도록 했다.

## 8. 백엔드 연결 체크리스트

- [ ] 모델 파일 3개를 동일 버전으로 배포
- [ ] 프로세스 시작 시 SHA-256 검증 후 한 번 로드
- [ ] 13개 필드·허용 범주·컬럼 순서 검증
- [ ] 빈값을 `Unknown`으로 정규화
- [ ] 다섯 기본 확률을 메타모델 입력 순서대로 결합
- [ ] 응답에 `won_probability`, `predicted_class`, `model_version` 포함
- [ ] 추론 지연시간과 오류 로그 기록
- [ ] 실제 승패 확정 후 결측률·확률 품질·FP/FN 모니터링
