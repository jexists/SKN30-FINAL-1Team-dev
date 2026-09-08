# 계약관리 → 일정관리 자율 위임 구현 계획과 작업 인수인계

## 현재 상태와 목표

- 이 PR은 구현 계획과 다른 노트북에서 사용할 작업 프롬프트를 전달하는 **문서 PR**이다. 자율 위임 기능은 아직 구현하지 않았다.
- 조사 기준: `origin/develop`의 `0ff0ab18f7e5e3b24fb157dc2f62f688c3cb883c` (2026-09-08).
- 다음 미팅 제안, 일정 후보 탐색, 제안 카드, 승인 후 일정 등록은 이미 존재한다. 새로 만드는 기능이 아니다.
- 바꿀 것은 실행 결정권이다. 백엔드의 고정 체이닝을 계약관리 LLM의 도구 호출과 결과 기반 재판단으로 전환한다.
- 일정관리는 전문 도구로 호출되는 하위 에이전트로 유지한다. 계약 선별·브리핑의 기능 확장, 전역 에이전트 플랫폼, 새로운 프레임워크 도입은 범위 밖이다.

## 확인한 코드와 변경 지점

| 파일 (저장소 루트 기준) | 현재 역할 / 계획 |
| --- | --- |
| `backend/app/agents/contract_management.py` | `propose_next_meeting()`의 단일 구조화 생성 호출을 도구 사용 루프로 변경. 기존 위험 근거 검증·출력 필드는 유지하고 프롬프트 버전 갱신 |
| `backend/app/agents/schedule_management.py` | 기존 `run()`과 업무시간·충돌·길이 후처리 재사용 |
| `backend/app/services/llm.py` | 기존 `configured_chat_model()` 재사용. 공통 `generate_structured()`를 모든 에이전트 대상으로 변경하지 않음 |
| `backend/app/agents/meeting_content_analysis.py` | 저장소의 `create_agent` 사용 방식 참고. 기존 의존성의 실제 API를 확인하고 구현 |
| `backend/app/services/contract_schedule_snapshots.py` | 부모 최종 출력 없이 도구 인자로 일정 스냅샷을 만드는 내부 경로 추가. 공통 조회·검증 재사용 |
| `backend/app/services/contract_schedule_delegation.py` (신규 제안) | 위임 인자 검증, 권한, 자식 실행 생성·실행·결과 반환을 담당하는 좁은 서비스 |
| `backend/app/services/agent_runs.py` | 실행 ID와 서버 실행 컨텍스트를 전달하고 계약관리 경로에 위임 콜백 주입 |
| `backend/app/services/agent_worker.py` | 부모 heartbeat·lease·실패·재시도와 자식 실행의 상호작용 검증 |
| `backend/app/services/contract_next_meeting_pipeline.py` | 고정 일정관리 호출 제거. 최종 선택된 자식 실행을 기존 제안 저장 함수에 연결 |
| `backend/app/models/agent.py`, `backend/app/schemas/agent_runs.py` | 실행 관계·출력 계약·중복 방지 제약 검토. 필요한 최소 변경만 적용 |
| `backend/app/api/contract_suggestions.py`, `backend/app/api/activities.py` | 후보 조회, 승인 시 후보·권한·충돌 재검증 및 후속 흐름 회귀 검증 |
| `frontend/src/api/contractAgent.ts`, `frontend/src/types/contractAgent.ts`, `frontend/src/pages/Calendar/useAiSuggestions.ts` | 기존 응답 계약과 중복 실행 여부 확인. 필요한 경우에만 최소 변경 |

## 목표 실행 흐름

```text
업무 이벤트 또는 기존 계약관리 요청
  → 계약관리 실행
  → 미팅 불필요/정보 부족이면 사유와 함께 종료
  → 미팅이 필요하면 request_schedule_candidates 도구 호출
      → 서버에서 권한·인자 검증 및 최신 일정 조회
      → 자식 일정관리 AgentRun 실행
      → 후보 또는 후보 없음 또는 실행 오류 반환
  → 계약관리가 결과를 읽고 최종 제안 또는 조건 조정 후 재위임
  → 검증된 최종 결과와 선택된 자식 실행 저장
  → 기존 제안 카드 → 사용자 승인 → 기존 일정 등록
```

## 1. 도구와 최종 출력 계약

`request_schedule_candidates`의 모델 입력은 다음으로 제한한다.

- `preferred_starts_at`, `preferred_ends_at`: 시간대가 명시된 탐색 기간.
- `duration_minutes`: 기존 허용 범위(5~480분) 내 미팅 길이.
- `reason`: 미팅 필요성과 해당 기간을 택한 이유.

사용자·팀·딜·부모 실행 ID는 서버 실행 컨텍스트에서 주입한다. 모델이 대상이나 권한을 변경할 수 없어야 한다. 시스템 트리거는 현재처럼 서버가 검증한 딜 담당자 컨텍스트를 사용하고, 사용자 트리거는 기존 접근 정책을 유지한다.

도구 결과에는 `status` (`candidates_found`, `no_candidates`, `failed`), 검증된 후보 목록, 안전한 사유 코드/설명, `schedule_run_id`, 실제 적용 탐색 조건을 포함한다. 원본 일정의 개인정보를 계약관리 모델에 되돌려 보내지 않는다.

최종 계약관리 출력은 기존 `risks`, `missing_information`, `recommended_actions`, `next_meeting_suggestion`을 보존하고, 최종 일정 처리 상태와 선택된 일정관리 실행을 식별할 최소 필드를 추가한다. 새 필드 명칭은 실제 Pydantic/API 소비처를 확인해 확정한다. 후보 원본은 자식 실행에 보관하고, 모델이 생성한 후보 사본을 신뢰하지 않는다.

## 2. 부모가 실행 중인 상태에서 위임하기

현재 일정 스냅샷은 부모 `output_snapshot.next_meeting_suggestion`에서 조건을 읽는다. 새 구조에서는 부모가 아직 완료되지 않았다. 부모를 조기 완료시키거나 임시 최종 출력을 기록하지 말고, 검증된 도구 인자를 직접 받는 내부 경로를 만든다.

기존 공개 API의 완료된 부모 검증은 약화하지 않는다. 내부 위임 경로만 실행 컨텍스트와 현재 부모 lease를 확인해 실행 중인 부모 아래 자식을 만든다. 순환 import를 피하도록 에이전트에는 서비스 전체 대신 좁은 async 실행 콜백을 전달한다.

현재 스냅샷에는 잘못된 날짜의 기본값 처리와 좁은 기간의 자동 확대가 있다. 도구 경로에서는 잘못된 입력을 명시적으로 반환해 모델이 수정하게 한다. 확정된 마감·사용자 제한은 자동 확대 때문에 넘어가지 않게 서버에서 검사한다. 선호 기간과 반드시 지켜야 하는 제한을 구별하며, 모든 계약 만료일을 무조건 일정 마감으로 추정하지 않는다.

## 3. 판단 루프와 제한

- 계약관리 LLM이 도구 호출 여부와 탐색 조건을 결정한다. 백엔드는 허용된 도구의 실제 실행과 검증을 담당한다.
- 최초 탐색 1회 + 조건을 바꾼 재탐색 1회, 최대 2회로 제한한다.
- 인자 오류를 포함한 전체 도구 요청 수와 전체 모델 단계에도 상한을 두어 잘못된 요청의 무한 반복을 막는다.
- 두 번째 탐색은 첫 결과를 근거로 조건 변경 사유를 포함해야 한다. 동일 조건을 반복 탐색하지 않는다.
- 후보가 없을 때 기간을 조정할 수 있지만, 서버에서 확정한 제약을 위반할 수 없다. 소요 시간을 근거 없이 줄여 성공을 만들지 않는다.
- 도구 오류는 후보 없음과 구분한다. 모델이 연결 오류를 피하려 조건을 바꾸며 반복하지 않게 한다.
- 최종 실행 ID는 현재 부모에 속한 완료된 자식인지, 실제 후보가 있는지 확인한다. 후보가 없는 응답에서 존재하지 않는 일정을 생성하지 않는다.
- 기존 LLM timeout 및 오류 코드 방식을 재사용하면서 전체 실행 시간도 제한한다.

## 4. 실행 기록, 중복 방지, 장애 복구

`parent_run_id`로 계약관리와 각 일정관리 시도를 연결한다. 저장할 것은 입력 조건, 정규화한 요청 식별자, 안전한 결과, 최종 선택된 자식 ID다. 모델 내부 사고 과정은 저장하지 않는다.

- 부모 ID + 정규화한 탐색 조건을 기준으로 동일 위임을 식별한다. 모델의 tool-call ID만으로 중복을 판단하지 않는다.
- 기존 unique 제약과 idempotency 필드를 먼저 확인한다. 충돌에 안전한 구현이 불가능하면 최소 SQL 마이그레이션으로 제약을 추가한다.
- 동일 자식이 completed이면 결과를 재사용한다. running이면 새 행을 만들지 않고 기존 실행을 제한된 시간 내 추적한다. failed이면 기존 worker의 일시 오류 재시도 정책을 따른다.
- 모델 재탐색 횟수와 worker의 네트워크 재시도 횟수는 별개다. 부모 재시작 뒤에도 전체 재탐색 한도를 DB 기록 기준으로 유지한다.
- 부모 재시도 시 기존 자식 조건과 결과를 컨텍스트에 복원한다. 모델이 다른 조건을 새로 생성해서 제한을 우회하지 않게 한다.
- 부모가 자식을 기다리는 동안 heartbeat가 유지되어야 한다. 자식은 기존 선점 절차로 실행하고 worker가 하나뿐이어도 교착되지 않도록 한다.
- LLM 호출 중 DB 트랜잭션을 오래 유지하지 않는다. 부모 lease를 잃었거나 취소된 실행은 새 위임과 최종 결과 저장을 중지한다.

## 5. 기존 기능 연결

기존 트리거와 딜 단위 쿨다운을 유지한다. 파이프라인에서 계약관리 뒤에 항상 일정관리를 실행하던 구간을 제거하고 계약관리 결과를 소비한다.

최종 선택된 자식의 ID를 기존 `ContractNextMeetingSuggestion.schedule_management_run_id`에 저장한다. 첫 탐색/재탐색 중 어떤 결과를 표시할지 모호하지 않게 한다. 후보 없음·정보 부족은 부모 실행 결과에 남기고 가짜 후보 카드를 만들지 않는다. 기존 제안이 남아 있을 때 갱신/유지/숨김 정책을 현재 코드에서 확인하고 오래된 후보가 새 성공 결과처럼 노출되지 않도록 테스트한다.

자동 이벤트 경로와 직접 계약관리 API 경로를 함께 확인한다. 이미 위임이 끝난 후 프런트엔드나 서비스가 일정관리를 다시 호출하는 경로가 있으면 제거한다. 단독 일정관리 기능은 유지한다. 사용자 승인, 승인 순간 충돌 재검증, 현재 브리핑 연동을 회귀 검증한다.

## 6. 구현 순서와 완료 조건

1. 기존 출력 소비처·권한·worker 실행 경로·DB 제약을 읽고 영향 범위를 확정한다.
2. 도구 입력/결과 모델과 부모 완료 없이 스냅샷을 만드는 내부 경로를 구현한다.
3. 자식 실행 서비스와 중복 방지·복구를 구현하고 모델 없이 검증한다.
4. 계약관리 도구 루프를 연결하고 모의 모델로 의사결정 분기를 검증한다.
5. 고정 파이프라인을 제거하고 기존 제안 저장·조회·승인과 연결한다.
6. 관련 테스트, lint, diff 검사를 실행하고 합성 데이터 기반 실호출은 별도 결과로 보고한다.

| 시나리오 | 완료 기준 |
| --- | --- |
| 미팅 불필요 / 정보 부족 | 일정관리 실행 없음, 종료 사유 기록 |
| 최초 탐색 성공 | 자식 1개, 실제 후보와 연결된 제안 카드 |
| 후보 없음 후 재탐색 성공 | 서로 다른 조건의 자식 2개, 최종 선택 결과가 카드에 반영 |
| 두 번 모두 후보 없음 | 세 번째 호출 없음, 조정 필요 결과 |
| 잘못된 날짜 / 제한 초과 / 다른 팀 접근 | 서버에서 차단, 잘못된 자식 또는 일정 미생성 |
| 도구 연결 오류 | 후보 없음과 구분, 안전한 오류 기록 |
| 부모 재시도 / 동시 중복 요청 | 같은 조건의 자식 중복 미생성, 완료 결과 재사용 |
| 부모 재시작 / lease 상실 | 횟수 제한 복원, 상실한 실행의 추가 쓰기 차단 |
| 위조 자식 ID / 후보 | 다른 부모·팀 또는 존재하지 않는 후보 거부 |
| 기존 승인 / 단독 일정관리 / 브리핑 | 기존 계약과 동작 유지 |

관련 기존 테스트: `test_contract_management.py`, `test_schedule_management.py`, `test_contract_schedule_snapshots.py`, `test_contract_next_meeting_pipeline.py`, `test_contract_schedule_pipeline.py`, `test_contract_suggestions.py`, `test_agent_runs.py`, `test_activities.py`. 신규 위임 서비스/루프 테스트를 필요한 파일에 추가한다. 실제 파일 존재 여부와 marker를 구현 시작 시 다시 확인한다.

로컬 준비는 Python 3.13 이상과 uv를 사용하며 `backend/pyproject.toml`, `backend/uv.lock`을 따른다. `.env`를 다른 기기에서 복사해 PR에 넣지 않는다. DB 테스트는 `docs/technical/local-test-database.md`를 읽고 해당 노트북의 격리된 테스트 DB를 준비한다. 문서에 기록된 다른 기기의 기존 DB가 현재 기기에도 있다고 가정하지 않는다.

예시 검사 (저장소 루트에서 `cd backend` 후 실행):

```sh
uv sync --frozen
uv run pytest tests/test_contract_management.py tests/test_schedule_management.py tests/test_contract_schedule_snapshots.py tests/test_contract_next_meeting_pipeline.py tests/test_contract_schedule_pipeline.py tests/test_contract_suggestions.py tests/test_agent_runs.py -q -m 'not integration'
uv run ruff check app/agents/contract_management.py app/services/contract_schedule_delegation.py app/services/contract_schedule_snapshots.py app/services/contract_next_meeting_pipeline.py app/services/agent_runs.py app/services/agent_worker.py
```

이 명령은 후속 구현용이며 이 문서 PR에서 실행한 테스트가 아니다. 새 테스트 파일과 실제 수정 파일을 검사 대상에 추가한다. DB와 외부 LLM이 필요한 검사는 설정·사용 데이터·marker를 먼저 확인하고 분리 실행한다. 테스트가 환경 부족으로 실패하면 해당 사유를 명시하며 성공으로 보고하지 않는다.

## 다른 노트북에서 바로 붙여 넣을 프롬프트

아래 프롬프트를 저장소가 열린 Codex 또는 Claude Code에 전달한다.

```text
SalesLuv의 계약관리 → 일정관리 자율 위임을 실제로 구현해줘.

인수인계 문서는 docs/technical/multiagent/contract-schedule-delegation-handoff.md다.
문서가 없다면 먼저 origin의 jiyu-park/contract-schedule-delegation-plan 브랜치에서
해당 문서와 PR을 읽어라. 이 문서 PR은 계획만 작성한 상태이며 기능 구현은 아직 없다.

목표는 기존 다음 미팅 제안 기능을 새로 만드는 것이 아니다.
계약관리 LLM이 미팅 필요성을 판단하여 request_schedule_candidates 도구로
기존 일정관리 에이전트에 위임하고, 반환 결과에 따라 최종 제안 또는 조건 변경 후
재위임을 결정하도록 기존 고정 파이프라인을 전환하는 것이다.

시작할 때:
1. AGENTS.md와 .agent-rules/branching.md를 읽고 git 상태·열린 PR·최신 develop을 확인해라.
2. 다른 작업의 변경은 건드리지 마라. 이 문서 PR이 미병합이면 문서를 참고하되
   최신 develop 기반의 별도 구현 브랜치/worktree에서 작업한다. 미병합 코드 의존성이
   실제로 필요하면 임의 복사하지 말고 의존성을 먼저 확인한다.
3. 브랜치 이름은 인증된 GitHub login을 사용한 저장소 규칙을 따른다.
4. 인수인계 문서의 기준 커밋 이후 변경을 확인하고 현재 코드와 차이가 있으면 계획을 보정한다.

구현 요구사항:
- 기존 configured_chat_model 및 저장소의 도구 사용 패턴과 일정관리 후처리를 재사용한다.
- 계약관리에만 좁은 도구 사용 루프를 연결한다. 새로운 범용 프레임워크를 만들지 않는다.
- 도구 인자는 기간·길이·이유뿐이다. 사용자·팀·딜·부모 실행은 서버에서 주입하고 검증한다.
- 부모는 아직 running이므로 완료된 부모 출력에 의존하지 않는 내부 스냅샷 경로를 만든다.
  공개 API의 기존 부모 완료/권한 검증은 약화하지 않는다.
- 후보 있음/없음/실행 오류를 구분하고 최대 두 번 탐색한다.
  인자 오류를 포함한 전체 단계에도 제한을 두고 확정된 제약을 넘지 않게 한다.
- 각 위임은 부모 아래 자식 AgentRun으로 남긴다. 부모 재시도·동시 실행에서도
  동일 조건 중복 실행을 방지하고 횟수·결과를 복구한다.
- worker 하나에서도 교착되지 않아야 하며 부모 heartbeat·lease·취소 처리를 유지한다.
- 최종 자식 ID와 후보는 해당 부모·팀에 속한 실제 성공 결과인지 검증한다.
- 파이프라인의 무조건적인 일정관리 호출을 제거하고 선택된 자식 ID를 기존 제안에 연결한다.
- 직접 API와 자동 이벤트 모두 중복 위임 여부를 확인한다.
- 캘린더, 단독 일정관리, 승인 순간 충돌 검증, 현재 브리핑 흐름을 유지한다.
- 실제 고객 데이터·비밀값은 커밋하거나 외부 모델에 추가 전송하지 않는다.

설명이나 계획 재작성에서 멈추지 말고 구현과 관련 검증까지 완료해라.
문서의 테스트 시나리오를 기준으로 모의 모델 단위 테스트와 격리 DB 검증을 진행하고,
실제 LLM 검증은 합성 데이터와 사용 가능한 설정으로만 수행해라.
실행하지 못한 검사는 이유를 명시해라. 원격 DB를 임의로 수정하지 마라.

완료 시 수정 내용, 테스트 결과, 남은 제약과 변경 파일을 보고하고
이 문서의 구현 상태도 실제 결과에 맞게 갱신해라.
이 프롬프트만으로 커밋·푸시·새 PR·병합을 수행하지 말고,
그 작업은 후속 사용자가 요청했을 때 저장소 Git 규칙에 따라 진행해라.
```
