# 딜 승산 이진 분류 데이터 전처리 및 AI 학습 모델

> SalesLuv ML Model Report
>
> 검증 기준일: 2026-08-17

## 1. 결정 요약

| 항목 | 결정 |
|---|---|
| 학습 문제 | 딜 성사 여부 `Won / Lost` 이진 분류 |
| 학습 데이터 | Salvirt B2B Sales Dataset |
| 입력 | 22개 후보 특성 중 10개로 1차 테스트 |
| 전처리 | 중복 제거, One-Hot Encoding, 그룹 분할 |
| 1차 기준 모델 | One-Hot + Logistic Regression(`C=0.1, L2`) |
| 최종 모델 | 입력 특성 재검토 및 하이퍼파라미터 튜닝 후 확정 |
| 출력 | 계약가능성 이진 분류 `계약가능성 높음` / `계약가능성 주의` |
| 사용 범위 | 화면에 참고 정보로만 표시 |

이 모델은 STT나 미팅 원문을 직접 학습하는 NLP 모델이 아닙니다. 미팅 분석 Agent가 원문과 CRM 정보에서 범주형 특성을 구성하고, ML 모델은 그 구조화된 값만 입력받습니다.

현재는 단일 미팅에서 비교적 추출 가능한 10개 특성으로 1차 테스트를 진행했으며, 향후 22개 전체 특성으로 확장해 적용할 예정입니다.

## 2. 학습 목적과 사용 범위

- 입력: 현재 10개 특성(향후 22개 후보 전체)
- 정답: 영업 딜 성사 `Won=1`, 취소 `Lost=0`
- 출력: 계약가능성 이진 분류(`계약가능성 높음` / `계약가능성 주의`)
- 활용: 고객 및 진행 딜 화면에 표시
- 제외: 영업 단계·실제 계약의 자동 변경, 다른 Agent 실행, 담당자 평가

> 출력값은 공개 데이터의 패턴을 기준으로 계산한 참고값이며, SalesLuv 환경의 실제 영업 딜 성사 여부를 보장하지 않습니다.

## 3. 학습 데이터

[Salvirt B2B Sales Dataset](https://www.salvirt.com/research/b2bdataset/)을 사용합니다. 대화 원문이 아니라 범주형 딜 조건과 최종 결과로 구성된 공개 B2B 영업 데이터입니다.

| 항목 | 확인 결과 |
|---|---:|
| 원본 행 | 448건 |
| 전체 컬럼 | 23개 |
| 입력 특성 | 범주형 22개 |
| 정답 컬럼 | `Status` |
| 빈값 | 0건 |
| 중복으로 제거되는 행 | 83건 |
| 중복 제거 후 | 365건 |
| `Won` | 173건 |
| `Lost` | 192건 |

`Won` 173건과 `Lost` 192건으로 정답 비율이 비슷합니다. 따라서 SMOTE, 임의 데이터 증강, class weight는 적용하지 않습니다.

## 4. 전체 입력 후보 22개

현재는 22개 후보 컬럼을 전체로 관리하고, 1차 테스트에서는 미팅에서 상대적으로 추출 가능한 10개만 사용합니다. 향후 22개 입력 스키마 확장을 목표로 운영합니다.

### 4.1 현재 1차 테스트 특성 10개

| 원본 컬럼 | 의미 | 원본 범주 |
|---|---|---|
| `Authority` | 의사결정권자 수준 | High / Mid / Low |
| `Competitors` | 경쟁사 검토 여부 | Yes / No / Unknown |
| `Purch_dept` | 구매부서 관여 여부 | Yes / No / Unknown |
| `Budgt_alloc` | 예산 확보 여부 | Yes / No / Unknown |
| `Forml_tend` | 공식 입찰 여부 | Yes / No |
| `RFI` | 정보요청서 진행 여부 | Yes / No |
| `RFP` | 제안요청서 진행 여부 | Yes / No |
| `Posit_statm` | 명시적인 긍정 구매 표현 | Yes / No / Neutral |
| `Scope` | 계약 범위 구체화 정도 | Clear / Few questions / Low |
| `Needs_def` | 고객 요구사항 구체화 정도 | Yes / Poor / Info gathering / No |

### 4.2 추가 적용 후보 12개

- `Product`: 추후 적용
- `Seller`: 추후 적용
- `Comp_size`: 추후 적용
- `Partnership`: 추후 적용
- `Growth`: 추후 적용
- `Source`: 추후 적용
- `Client`: 추후 적용
- `Strat_deal`: 추후 적용
- `Cross_sale`: 추후 적용
- `Up_sale`: 추후 적용
- `Deal_type`: 추후 적용
- `Att_t_client`: 추후 적용

### 향후 처리 원칙

- 22개 컬럼 중 미팅 또는 CRM에서 확인 가능한 값은 실제 범주값을 기록합니다.
- 확인되지 않으면 `Unknown`으로 통일해 처리합니다.
- `Product`, `Seller`는 SalesLuv 상품/담당자 매핑 규칙이 정해진 뒤 적용합니다.

## 5. 데이터 전처리

전처리는 다음 순서로 진행합니다.

1. 컬럼명과 문자열의 앞뒤 공백을 정리합니다.
2. 정답을 `Won=1`, `Lost=0`으로 변환합니다.
3. 23개 컬럼 값이 모두 같은 완전 중복 행 83건을 제거합니다.
4. 1차 테스트에서는 선정한 10개 입력 특성만 사용합니다.
5. 향후 22개 전체 컬럼에서는 확인되지 않은 값을 `Unknown`으로 처리합니다.
6. `Unknown`을 하나의 유효한 범주로 유지합니다.
7. 범주형 특성을 One-Hot Encoding으로 변환합니다.
8. 1차 테스트는 10개 조합으로 그룹을 지정하고, 확장 테스트는 22개 조합으로 재설정합니다.

모든 입력이 범주형이므로 평균값 대체와 수치 정규화는 적용하지 않습니다.

미팅에서 확인할 수 없는 값을 `No`로 가정하지 않고 `Unknown`으로 처리합니다. 원본에 `Unknown`이 없는 특성은 `OneHotEncoder(handle_unknown="ignore")`로 처리합니다.

## 6. 학습·검증 방식

행 단위 무작위 분할은 사용하지 않습니다. 동일 특성 조합이 학습과 평가 데이터에 나뉘면 같은 입력을 미리 보게 되어 성능이 부풀려질 수 있습니다.

- 10개 특성 조합이 같은 행을 하나의 그룹으로 설정
- 그룹 분할 시 학습·평가 겹침 없음 보장: `StratifiedGroupKFold`
- 5-Fold 교차검증을 시드 10회 반복
- 총 50개 평가 fold 평균으로 모델 비교

선택한 10개 특성 기준으로 중복 제거 후 365행은 133개의 고유 특성 조합으로 구성됩니다. 같은 특성 조합인데 실제 결과가 `Won`과 `Lost`로 다른 사례도 있어, 현재 입력만으로 모든 딜을 완벽히 구분할 수는 없습니다.

### 평가 지표

1. `ROC-AUC`: 승산이 높은 딜을 더 위에 배치하는 능력
2. `Brier Score`: 예측 확률과 실제 결과의 일치 정도
3. `Accuracy`: 전체 예측 중 정답 비율

`Brier Score`는 낮을수록 좋고, 나머지 지표는 높을수록 좋습니다. 분류 결과의 순위와 확률적 품질을 함께 보는 기능이므로 단일 정확도보다 `ROC-AUC`와 `Brier Score`를 우선합니다.

## 7. 10개 특성 기준 1차 모델 비교

현재 선정한 10개 특성으로 후보 모델을 간단히 비교한 초기 결과입니다. 22개 특성 확장과 튜닝 전의 기준값이며 최종 모델 확정 결과가 아닙니다.

| 모델 | ROC-AUC | Brier Score | Accuracy |
|---|---:|---:|---:|
| Dummy 기준 모델 | 0.500 | 0.249 | 52.6% |
| One-Hot + Logistic Regression | 0.793 | 0.190 | 71.0% |
| CatBoost | 0.792 | 0.191 | 72.0% |
| One-Hot + MLP 신경망 | 0.785 | 0.197 | 70.6% |

1차 기준에서는 Logistic Regression와 CatBoost의 성능 차이가 거의 없습니다.

## 8. 1차 기준 모델

`OneHotEncoder(handle_unknown="ignore") + LogisticRegression(C=0.1, L2)`

선정 이유는 다음과 같습니다.

- CatBoost와 거의 같은 ROC-AUC를 보이면서 Brier Score는 더 좋음
- MLP 신경망보다 검증 성능이 높음
- 현재 데이터 규모에 적합
- 모델의 입력과 영향이 설명되기 쉬움
- 추가 학습 인프라 없이 가볍게 운영 가능

현재 비교에서는 1차 기준 모델로 Logistic Regression을 우선 적용합니다. 최종 모델은 특성 조합 재검토, 하이퍼파라미터 튜닝, 추가 검증 후 확정합니다.

## 9. 실제 입력과 계약가능성 분류

`STT·메모·직접 입력 → 미팅 분석 Agent → 특성 구성(현재 10 / 향후 22) → ML 모델 → 계약가능성 분류`

ML 모델은 딜을 `계약가능성 높음`과 `계약가능성 주의` 두 부류로 구분해 화면에 표시합니다.

> 계약가능성 높음
>
> 실험 모델 · 미팅 내용 기반

분류 결과는 승인 없이 표시하지만 다른 Agent 실행이나 영업 딜 단계·실제 계약 변경에는 사용하지 않습니다.

실행 결과 저장(임시 예시)

- `agent_code`: `meeting_analysis`
- `source_refs`: 원천 `activity_id`, 대상 `sales_deal_id`
- `output_snapshot.deal_assessment`: 계산 시점의 10개 `features`, `label`, ML `model_version`
- 화면 표시: 같은 `sales_deal_id`의 완료 실행 중 `finished_at DESC, id DESC` 첫 행
- 재분석: 기존 실행을 덮어쓰지 않고 새 `agent_run` 행 추가

## 10. 한계와 향후 재학습

- 중복 제거 후 데이터가 365건으로 작습니다.
- 같은 특성 조합에서도 실제 영업 딜 결과가 다른 사례가 있습니다.
- 현재는 22개 후보 중 10개 특성만 사용해 1차 테스트했으며, 모델 비교와 튜닝 범위가 제한적입니다.
- 데이터는 SalesLuv의 한국어 영업 미팅이 아닌 외부 B2B 딜 데이터입니다.
- 원본에 각 범주의 세부 판정 기준이 부족해 미팅 분석 Agent에 일관된 변환 기준이 필요합니다.
- 따라서 현재 분류 결과는 기능 시연과 참고 용도로만 사용합니다.

### 실제 종료 딜 기반 재학습 기준

- `Won` 학습 표본: `sales_pipeline_stage.outcome_code=confirmed`이고 `contract_signed_on`이 있는 딜
  - 결과 시각: `contract_signed_on`
- `Lost` 학습 표본: `sales_pipeline_stage.outcome_code=cancelled`이고 `closed_on`이 있는 딜
  - 결과 시각: `closed_on`
- 결과 미정: `sales_pipeline_stage.outcome_code=in_progress`

재학습 시에는 결과가 난 뒤 정보가 입력에 섞이지 않도록 분류 시점의 특성과 이후 결과를 쌍으로 사용합니다. `Won`은 `contract_signed_on` 이전, `Lost`는 `closed_on` 이전에 생성된 분류만 표본으로 사용합니다. `closed_on`은 계약 체결일/매출 확정일로 해석하지 않습니다.

## 11. 데이터 사용 주의사항

[Hugging Face 데이터 카드](https://huggingface.co/datasets/markobo/B2B_Sales_data)에는 CC BY 4.0으로 표시되지만, Salvirt 공식 페이지에는 라이선스가 명확히 적혀 있지 않습니다.

- 문서와 발표에 Salvirt 출처를 표시합니다.
- 부트캠프 학습·시연 용도로 사용합니다.
- 원본 CSV는 공개 저장소에 올리지 않습니다.
- 상업적 사용이나 원본 재배포 전에는 Salvirt 사용 조건을 확인합니다.

## 참고 자료

- [Salvirt B2B Sales Dataset 공식 페이지](https://www.salvirt.com/research/b2bdataset/)
- [Hugging Face 미러 데이터 카드](https://huggingface.co/datasets/markobo/B2B_Sales_data)
