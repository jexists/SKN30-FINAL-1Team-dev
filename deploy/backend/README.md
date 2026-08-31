# 딜 승산 모델 배포 인계

현재 로컬 백엔드는 `deal-paper-rf-ensemble-v1`을 읽도록 연결했다. **AWS 업로드·배포는 아직 실행하지 않았다.**

## 올릴 파일

| 항목 | 값 |
|---|---|
| 파일 | `deal-paper-rf-ensemble-v1.joblib` |
| SHA-256 | `609c5d63b201fcb125cca9cddc2fcbe229f76d3ebf0a1417466d027248b17681` |
| EC2 디렉터리 | `/opt/salesluv-models/deal-paper-rf-ensemble-v1` |
| 컨테이너 경로 | `/app/pipeline/artifacts` — 읽기 전용 마운트 |
| 모델 | RF·LR·ExtraTrees·CatBoost를 결합한 LogisticRegression Stacking |
| 분류 임계값 | Won 확률 `0.5` 이상이면 `high`, 미만이면 `watch` |

기존 선정 모델을 그대로 사용한다. 미리 정한 첫 분할의 원본 거래 **357건 × 마스킹 10세트 = 3,570행**으로 학습했고, 이번 연결에서 재학습하거나 가중치를 변경하지 않았다. 마스킹은 학습·평가용이며 실제 요청에는 추가하지 않는다.

입력은 `Authority`, `Competitors`, `Purch_dept`, `Budgt_alloc`, `Forml_tend`, `RFP`, `Posit_statm`, `Source`, `Client`, `Scope`, `Cross_sale`, `Deal_type`, `Needs_def`의 **13개 범주형 값**이다. 미확인 값은 `Unknown`으로 전달한다. 허용 범주는 [로더의 입력 계약](../../backend/app/ml/deal_baseline.py)을 따른다.

별도 `.pkl`, `.json`, 원본 CSV, TabICL 체크포인트는 필요 없다. 인코딩 파이프라인·학습 모델·메타데이터가 위 `.joblib`에 들어 있다. 모델 파일은 Git에 추가하지 않는다.

## 배포 순서와 권한

1. 로더·`pyproject.toml`·`uv.lock`·배포 스크립트 변경을 **함께 `develop`에 병합**하고 CI를 확인한다. 파일 이름만 기존 버전으로 바꿔 끼우지 않는다.
2. 파일명과 위 디렉터리는 `v1` 그대로 유지하며 `v2` 파일을 만들지 않는다. 같은 경로에 파일을 교체할 때는 기존 파일을 먼저 별도 백업한다. 디렉터리는 `0755`, 파일은 `0644`로 두고 신뢰할 수 있는 관리자(예: `root`)가 소유한다. 상위 디렉터리도 컨테이너 UID `10001`이 탐색할 수 있어야 하며, 앱 사용자는 파일을 수정할 수 없어야 한다.
3. 코드와 모델 준비가 끝난 뒤 기존 [Backend 수동 배포 절차](../../docs/technical/deploy/deployment.md#62-backend-배포)를 실행한다. 배포 스크립트는 파일 존재·SHA를 확인하고, 후보 컨테이너에서 모델 검사까지 성공해야 트래픽을 전환한다. 누락·해시 불일치·추론 검사 실패 시 전환하지 않는다.
4. 이전 `deal-stacking-lr-v1` 디렉터리와 파일은 롤백용으로 남긴다. 이후 같은 `deal-paper-rf-ensemble-v1.joblib`의 내용만 교체할 때도 코드의 SHA와 합성 입력 기대값을 함께 맞춘다. 이전 코드로 롤백할 경우 그 코드에 대응하는 모델 백업도 복원해야 한다.

Joblib은 역직렬화 중 코드를 실행할 수 있으므로, 출처를 확인한 위 해시의 파일만 사용한다. 운영 의존성에는 Torch·TabICL이 없으며 노트북 학습 환경은 별도로 유지한다.

## 배포 전 모델 검사

`deploy.sh`는 새 후보 컨테이너에서 다음 명령을 `docker exec`로 실행하며 최대 300초로 제한한다.

```bash
/app/.venv/bin/python -c 'from app.ml.deal_baseline import _load_models; _load_models()'
```

이 검사는 파일 해시·입력 계약·클래스를 확인하고, 정상 범주·4개 `Unknown`·전체 `Unknown`인 고정 합성 입력의 확률이 저장 모델의 기대값과 같은지 확인한다. **모델 로딩·추론 호환성 검사이며 Accuracy·AUC 등 성능을 새로 평가하는 검사가 아니다.**

로컬 검증 완료: 실제 Linux x86_64 배포 이미지에서 UID `10001`·읽기 전용 모델 마운트로 로딩·예측 및 미팅 분석 Agent 연결을 확인했다(LLM 응답만 대체). Torch·TabICL이 없는 환경에서도 동일한 합성 입력 확률을 재현했다. 백엔드 테스트 435개와 Ruff·배포 셸 검사가 통과했으며, 외부 DB·LLM 설정이 필요한 테스트 8개는 실행하지 않았다. AWS 서버에서의 검사는 실제 배포 때 별도로 수행한다.

두 ML 보고서와 제출용 DOCX·PDF는 이 로더 연결 전의 학습 결과 기록으로 보존한다. 최신 배포 연결 상태는 이 문서를 기준으로 확인한다.
