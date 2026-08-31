# B2B 영업 승패 모델 노트북

현재 기준은 **13개 컬럼을 유지한 RF 베이스라인 → RF 튜닝 → TabICL 없는 분류 앙상블 비교**다. 상세한 결과와 저장 파일 계약은 아래 두 보고서를 기준으로 확인한다.

- [머신러닝·딥러닝 학습결과서](../../docs/technical/머신러닝_딥러닝_학습결과서.md): 데이터·전처리 이유·평가 설계·전체 비교 결과
- [학습한 ML/DL 모델 산출물](../../docs/technical/학습한_ML_DL_모델_산출물.md): 입력 계약·저장 후보·재로드 검증·배포 전 남은 범위

## 현재 실행 순서

| 순서 | 노트북 | 역할 |
|---|---|---|
| 1 | [deal_data_preprocessing.ipynb](deal_data_preprocessing.ipynb) | 원본 448건 유지, 13개 입력과 동일 입력 그룹 정의, 행당 `Unknown` 4개인 서로 다른 마스킹 10세트 준비 |
| 2 | [deal_model_paper_rf_baseline.ipynb](deal_model_paper_rf_baseline.ipynb) | 논문의 RF·30회 반복 분할 방식을 참고한 베이스라인 평가 및 기준 파일 저장 |
| 3 | [deal_model_paper_rf_tuning.ipynb](deal_model_paper_rf_tuning.ipynb) | 같은 30개 외부 분할의 Train 내부에서 5-Fold 그룹 CV로 RF 하이퍼파라미터 선택 |
| 4 | [deal_model_paper_rf_ensemble.ipynb](deal_model_paper_rf_ensemble.ipynb) | RF·LR·ExtraTrees·CatBoost 및 Soft Voting·Stacking 7개 후보 비교와 후보 저장 |

모델 노트북은 실행할 때 전처리 노트북을 불러온다. 베이스라인·튜닝 노트북이 저장한 로컬 파일은 다음 단계가 사용하므로 위 순서를 따른다. 각 파일은 전용 Jupyter 커널에서 위부터 실행한다.

```bash
uv sync --project backend/notebooks --locked
uv run --project backend/notebooks --locked jupyter lab backend/notebooks/deal_model_paper_rf_baseline.ipynb
```

원본 CSV 위치가 기본값과 다르면 커널을 시작하기 전에 `SALESLUV_B2B_DATA_PATH`를 지정한다. 학습 원본과 `backend/pipeline/artifacts/`의 모델 파일은 Git에 추가하지 않는다.

## 평가·저장 결과를 읽는 기준

- 최신 RF 흐름은 전처리의 전체 `X_all_masked_sets`, `y`, `input_group_ids`를 사용한다. 전처리에 남아 있는 7:3 분할(Train 313건/Test 135건)은 이전 실험용이며 최신 RF 평가에 사용하지 않는다.
- 외부 분리는 **동일 입력 그룹 기준 8:2를 30회 반복**한다. 행 수가 그룹마다 달라 매회 거래 건수가 정확히 8:2가 되는 것은 아니다. 같은 원본 입력과 마스킹 변형은 Train/Test 및 내부 Fold 사이에 섞이지 않는다.
- RF·추가 단일 모델의 파라미터는 각 외부 Train 내부에서 `neg_brier_score`로 선택한다. 분류 임계값은 `0.5`를 유지하며 Accuracy·AUC·Precision·Recall·F1·FP·FN도 함께 비교한다.
- Test 마스킹 10세트는 새로운 거래 10배가 아니다. 각 분할의 10세트 평균을 낸 뒤 30회 결과를 평균한다. 최종 후보의 선택도 이 비교를 사용했으므로, 완전히 새로운 최종 검증 결과로 해석하지 않는다.
- 논문과 입력 컬럼·마스킹·그룹 분리 조건이 다르고 논문의 정확한 RF 파라미터는 확인되지 않았다. 논문 모델의 완전한 재현이나 동일 조건의 성능 비교가 아니다.
- 저장된 `deal-paper-rf-ensemble-v1.joblib`은 미리 정한 첫 분할의 Train으로 학습한 검토 후보다. 30회 평균은 학습·평가 절차의 비교값이지 저장 파일 한 개의 Test 성능이 아니다. 전체 448건 재학습과 실제 서비스 배포는 아직 하지 않았으며, 후속 로컬 연결 상태는 아래에 구분한다.
- 실제 서비스 입력에는 임의의 4개 마스킹을 적용하지 않는다. 구조화 Agent가 확인하지 못한 값만 `Unknown`으로 전달한다.

## 이전 실험 기록

아래 파일은 경로·코드·저장 출력을 유지한 이전 실험이다. 현재 실행 순서의 필수 단계가 아니며 결과를 최신 RF 비교표에 섞지 않는다.

| 노트북 | 보존 이유 |
|---|---|
| [deal_model_phase2.ipynb](deal_model_phase2.ipynb) | TabICL을 포함한 이전 모델 비교 |
| [deal_model_phase3.ipynb](deal_model_phase3.ipynb) | 이전 5개 모델 튜닝 |
| [deal_model_phase4.ipynb](deal_model_phase4.ipynb) | 이전 반복 Group CV 앙상블 비교 |
| [deal_model_phase5_threshold.ipynb](deal_model_phase5_threshold.ipynb) | 이전 Stacking의 임계값 민감도 검토 |
| [deal_model_finalization.ipynb](deal_model_finalization.ipynb) | 기존 백엔드용 `deal-stacking-lr-v1` 재학습·저장 과정 |
| [deal_model_random_forest.ipynb](deal_model_random_forest.ipynb) | 단일 7:3 분할에서 수행한 초기 RF 실험 |
| [deal_model_random_forest_ensemble.ipynb](deal_model_random_forest_ensemble.ipynb) | 초기 RF와 기존 고정 파라미터의 앙상블 실험 |
| [deal_model_no_tabicl.ipynb](deal_model_no_tabicl.ipynb) | 기존 앙상블에서 TabICL만 제외한 비교 |

로컬 백엔드 로더 [`app/ml/deal_baseline.py`](../app/ml/deal_baseline.py)와 배포 스크립트는 `deal-paper-rf-ensemble-v1.joblib` 단일 파일을 사용하도록 연결했고 Linux x86_64 컨테이너 검증을 완료했다. 선정 당시의 학습 가중치와 임계값 `0.5`는 유지했다. 2026-08-31 기준 AWS 파일 배치는 사용자 확인 기준 완료됐지만 실제 서비스 배포·AWS 실행 검증은 미완료다. 두 ML 보고서와 제출용 DOCX·PDF는 학습 기록과 후속 연결 상태를 구분하며, 최신 상태와 파일·권한·배포 순서는 [배포 인계](../../deploy/backend/README.md)를 기준으로 확인한다.
