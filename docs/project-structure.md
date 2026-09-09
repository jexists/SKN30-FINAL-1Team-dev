# 프로젝트 구조

최상위 폴더의 역할과 미팅·보고서 처리의 주요 진입점을 설명합니다.

| 폴더 | 역할 |
|---|---|
| `backend/` | FastAPI 서버·에이전트·데이터 처리·SQL |
| `data/` | 로컬 수집 원본과 가공 데이터 |
| `demo/` | React 전 정적 화면 목업 |
| `deploy/` | 배포 설정 |
| `docs/` | 프로젝트 문서 |
| `final/` | 제출 완료 자료 |
| `frontend/` | React 앱 |
| `scripts/` | 로컬 작업 스크립트 |
| `test/` | 프론트엔드와 백엔드를 함께 쓰는 테스트 |

비어 있는 폴더는 현재 기능을 의미하지 않습니다. 새로운 구조를 미리 만들지 말고 실제 구현이 생길 때 추가합니다.

ML 학습 순서와 이전 실험은 [노트북 안내](../backend/notebooks/README.md), 현재 모델 연결·배포 상태는 [배포 인계](../deploy/backend/README.md)를 참고합니다.

## 미팅·보고서 처리

| 위치 | 역할 |
|---|---|
| `backend/app/services/meeting_processing.py` | CRM·원문 고정 → 내용분석 → 보고서·특성 병렬 실행, 초안 반영·공통 메모 원자적 저장 |
| `backend/app/agents/meeting/content.py` | 구간 귀속·조건부 검토와 내용분석 실행 한도 |
| `backend/app/agents/meeting/transcript.py` | 원문 위치를 보존하는 구간 분할·분석 입력 계약 |
| `backend/app/agents/meeting/refinement.py` | 미해결 구간의 CRM 조회 도구·재귀속 |
| `backend/app/agents/meeting/features.py` | 딜별 13개 특성 구조화와 별도 ML 예측 |
| `backend/app/agents/reports/meeting.py` | 미팅 근거 범위별 작성·검토·선택 수정 |
| `backend/app/agents/reports/meeting_contract.py` | 미팅 보고서 입력·출력 계약과 근거·렌더링 검증 |
| `backend/app/agents/reports/meeting_tools.py` | 작성자의 동결 근거·CRM·이전 보고서 조회 도구 |
| `backend/app/agents/reports/period.py` | 일일·주간·월간 작성 → 검토 1회 → 선택 수정 1회, 하위 보고서 사용 |
| `backend/app/agents/reports/period_sources.py` | 기간 입력 검증·미팅 묶음 또는 하위 기간 제출본 조립 |
| `backend/app/agents/reports/harness.py` | 미팅·기간 보고서의 공통 작성 단계·호출 계측 |
| `backend/app/agents/reports/skills/` | 미팅 작성 규칙·합성 예시, 기간 공통 문체와 일일·주간·월간 작성 규칙 |
| `backend/app/schemas/meeting_content.py`, `backend/app/schemas/report_drafts.py` | 공통 미팅 근거 계약·기간 보고서 생성 출력 계약 |
| `backend/app/api/agent_runs.py`, `backend/app/services/agent_stream.py` | 실행 조회·적용 API와 SSE 임시 미리보기. 최종 실행 상태는 DB 기준 |
| `frontend/src/pages/Meetings/Compose.tsx`, `frontend/src/api/meetingStream.ts` | 딜별 초안·공통 메모 편집, 생성·SSE 표시·결과 적용 |

초안 저장과 사용자 제출은 별개입니다. 제출된 미팅 보고서는 계약관리로 전달하고 기간 보고서의 원천이 됩니다. 전체 구조와 한계는 [미팅·보고서 구조](technical/multiagent/미팅_내용분석_보고서작성_에이전트_구조_보고서.md)를 참고합니다.

실행은 `services/agent_runs.py`의 `dispatch()`에서 종류별로 연결합니다. 기간 보고서의 입력 종류 검증도 이 경계에 두며, 별도 전달 전용 에이전트 파일은 사용하지 않습니다. 권한·DB 조회는 기존 `services/meeting_context.py`와 `services/report_sources.py`, ML 실행은 `ml/deal_baseline.py`에 유지합니다. 작성 스킬은 `reports/skills/`의 MD에서, 역할별 지시와 실행 정책은 각 Python 에이전트에서 관리합니다.

## 계약·일정 관리

| 위치 | 역할 |
|---|---|
| `backend/app/services/contract_next_meeting_pipeline.py` | 트리거 큐잉과 "다음 미팅 제안 → 일정 후보" 백그라운드 연결 |
| `backend/app/services/contract_schedule_snapshots.py` | 위험 신호·선호 기간·브리핑 입력을 DB에서 조립 |
| `backend/app/services/schedule_conflicts.py` | 담당자 일정과 겹치는지 판정. 카드 조회와 승인 직후 안내가 **같은 함수**를 쓴다 |
| `backend/app/api/contract_suggestions.py` | 저장된 제안 조회·닫기. 조회할 때 지난 후보를 빼고 겹침을 표시한다 |
| `frontend/src/pages/Calendar/components/SuggestionPanel/` | 캘린더 "AI 추천 일정" 패널 |

추천은 트리거 시점에 미리 계산해 저장하므로 사용자가 볼 때는 낡아 있을 수 있습니다.
그래서 조회 시점에 후보가 지금도 유효한지 다시 봅니다 — 지난 후보는 빼고, 그 자리에 다른
일정이 잡힌 후보는 표시만 하며, 남은 후보가 없으면 카드를 그리지 않습니다. 판정 규칙을
`schedule_conflicts.py` 한 곳에 두는 이유는 조회와 승인이 다르게 판단하면 사용자가 이유를
알 수 없기 때문입니다. 자세한 내용은 [계약에이전트 설계 5.1](technical/multiagent/계약에이전트_설계.md)을 참고합니다.

## 문서

```text
docs/
├── planning/    기획·요구사항
├── technical/   ERD·아키텍처 등 기술 자료
├── research/    실험·비교·검토 결과
├── meetings/    회의록
├── legal/       서비스 이용약관·개인정보처리방침·법적고지 등 실사용 법적 문서
└── references/  외부 제공 자료와 제출 양식 안내

final/           제출이 끝난 자료
```

- 같은 문서의 작업본과 확정본을 여러 폴더에 복사하지 않습니다.
- 실제 데이터는 `data/raw/`, `data/processed/`에 로컬 보관하며 커밋하지 않습니다.
- 외부 제공 원본은 수정하지 않고, 공개 허가와 개인정보·메타데이터 검토 전까지 Git에 추가하지 않습니다.
