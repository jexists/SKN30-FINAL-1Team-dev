# 영업·계약관리 Agent 설계

> 이 문서는 `contract_management` Agent의 실행과 승인 계약을 정의한다. 공통 HTTP, 인증, polling, 중복 요청 방지, 트랜잭션 규칙은 [API conventions](../backend/api-conventions.md)를 따르고, 물리 데이터 관계는 [SalesLuv ERD](../SalesLuv_ERD.md)를 기준으로 한다.

## 1. 목적과 범위

고객사에 연결된 영업 딜, 계약 정보, 승인된 보고서, C/S와 최근 활동을 종합해 계약 현황과 위험을 설명하고 다음 행동을 제안한다.

- Agent 실행은 조회와 제안 생성까지만 수행한다.
- `completed`는 제안 생성 완료이며 계약 데이터 반영 완료가 아니다.
- 계약 번호, 계약일, 종료일, 파이프라인 단계 등 업무 데이터는 별도 사용자 승인 요청에서만 변경한다.
- 승인 전에는 `sales_deal`, `activity`, `support_request`를 수정하지 않는다.

## 2. 입력과 데이터 범위

필수 실행 기준은 `customer_company_id`이고 필요하면 대상 `sales_deal_ids`를 제한한다.

| 입력 묶음 | 원천 | 조건 |
|---|---|---|
| 고객사 | `customer_company` | 요청자와 같은 `team_id`, 삭제되지 않은 행 |
| 딜·계약 | `sales_deal`, `sales_pipeline_stage` | 고객사에 속하고 삭제되지 않은 딜 |
| 보고서 | `report`, `report_activity`, `activity` | `status_code='approved'`인 보고서만 사용 |
| C/S | `customer_contact`, `support_request`, `support_response` | 고객사 담당자를 통해 연결된 같은 팀 데이터 |
| 최근 활동 | `activity` | 대상 딜과 연결되고 삭제되지 않은 활동 |

앞 단계 보고서가 없거나 일부 필드가 비어 있어도 실행은 실패하지 않는다. 확인되지 않은 사실을 추측하지 않고 `missing_information`에 부족한 항목을 남긴다.

## 3. Agent 실행 계약

`agent_run`에는 다음을 저장한다.

- `agent_code`: `contract_management`
- `source_refs`: `customer_company_id`, 조회한 `sales_deal_ids` 등 식별자
- `input_snapshot`: 실제 판단에 사용한 값과 stale 검증 대상의 `id`, `updated_at`
- `output_snapshot`: 계약 요약, 위험, 누락 정보, 권장 행동, 다음 미팅 제안
- `evidence`: 결과 항목과 원천 ID의 대응 관계. 고객 원문 전체는 복제하지 않는다.

```json
{
  "contract_summary": {},
  "risks": [
    {
      "code": "contract_expiring",
      "severity": "high",
      "message": "string",
      "source_refs": [{"type": "sales_deal", "id": "uuid"}]
    }
  ],
  "missing_information": [],
  "recommended_actions": [],
  "next_meeting_suggestion": {
    "sales_deal_id": "uuid",
    "reason": "string",
    "preferred_starts_at": "2026-08-24T09:00:00+09:00",
    "preferred_ends_at": "2026-08-28T18:00:00+09:00",
    "duration_minutes": 60
  }
}
```

> **구현 참고 (2026-08-24):** `preferred_date_range` 객체 대신 `preferred_starts_at`/`preferred_ends_at`
> flat 필드로 구현했다(`backend/app/agents/contract_management.py`의 `NextMeetingSuggestion`).
> 위 예시는 실제 구현 기준으로 갱신했다.

위험 코드와 심각도 값은 구현 전에 enum으로 고정한다. 자유 문구만으로 업무 분기를 만들지 않는다.
**확정 (2026-08-24):** §10.1 결정에 따라 `ContractRisk.code`를 6개 값의 `Literal` enum으로
고정했고, 심각도는 `backend/app/services/agent_runs.py`의 `_contract_source`가 결정론적으로
계산해 `risk_signals`로 전달한다. 아래 §10.1을 참고한다.

## 4. 권한 검증

1. 요청자가 활성 회원인지 확인한다.
2. 대상 고객사와 모든 딜이 요청자의 `team_id`에 속하는지 확인한다.
3. 보고서, 활동, C/S를 같은 팀과 대상 고객사 관계로 다시 제한한다.
4. 다른 팀 데이터는 존재 여부를 노출하지 않고 `404`로 처리한다.
5. 실행 조회와 승인에도 동일한 팀 검증을 반복한다.

## 5. 승인과 실제 반영

승인 요청은 Agent 실행 요청과 분리한다. 승인 API의 구체적인 경로와 요청 schema는 구현 시 확정하되 다음 순서를 지킨다.

> **구현 확정 (2026-08-24):** §10.2 결정에 따라 계약관리 Agent 자체에는 이 순서를 따르는
> 승인 엔드포인트를 만들지 않았다. 아래 원칙(승인·실행 분리, stale 재검증, 트랜잭션 반영)은
> 일정관리 실행의 `POST /api/agent-runs/{agent_run_id}/approvals`가 그대로 구현했다 —
> 상세는 §10.2·§10.3과 [일정관리 Agent 설계](일정관리_Agent_설계.md) §6을 참고한다.

1. `agent_run`이 같은 팀의 `contract_management` 실행인지 확인한다.
2. 실행 상태가 `completed`인지 확인한다.
3. 승인 요청에 사용자가 선택하거나 수정한 최종 값을 받는다.
4. `input_snapshot`의 stale 대상 값과 현재 DB 값을 비교한다.
5. 권한, FK, 현재 상태와 업무 규칙을 다시 검증한다.
6. 한 DB 트랜잭션에서 선택된 업무 데이터만 반영하고 감사 가능한 실행 ID를 남긴다.
7. 같은 승인 요청의 중복 반영을 막는다.

Agent 출력 전체를 그대로 저장하지 않고, 서버가 허용한 필드만 명시적 schema로 받아 반영한다.

## 6. stale 판정

다음 중 하나라도 달라졌으면 반영하지 않고 `409 stale_agent_result`를 반환한다.

- 대상 행이 삭제되거나 다른 상태로 전이됨
- 비교 대상으로 저장한 `updated_at`이 현재 값과 다름
- 계약 단계, 계약일, 종료일 등 제안 근거 필드가 달라짐
- 승인 보고서의 상태나 내용 버전이 달라짐

stale 발생 시 기존 `agent_run`을 수정하거나 덮어쓰지 않는다. 사용자는 최신 데이터로 새 실행을 요청해야 한다.

## 7. 오류 계약

실행 조회, 완료 상태, stale, 중복 요청 방지, 요청 검증과 LLM 장애는 [공통 Agent 오류](../backend/api-conventions.md#141-공통-agent-오류)를 따른다. 이 Agent에는 다음 도메인 오류만 추가한다.

| 상태 | `detail` | 조건 |
|---:|---|---|
| `404` | `customer_company_not_found` | 대상이 없거나 다른 팀 소속 |
| `404` | `sales_deal_not_found` | 대상 딜이 없거나 고객사·팀 범위와 일치하지 않음 |

## 8. 구현 파일 경로

미팅분석과 보고서작성 Agent처럼 핵심 Agent 로직만 `app/agents`에 분리하고, 실행 요청·상태 관리·polling은 기존 `agent_runs` 파일을 확장한다. 계약 데이터의 실제 반영은 Agent API가 아니라 기존 영업 딜 리소스가 담당한다.

| 역할 | 기존 패턴에 맞춘 경로 |
|---|---|
| 핵심 Agent 로직·출력 모델 | `backend/app/agents/contract_management.py` 새 파일 |
| 실행 요청·응답 schema | `backend/app/schemas/agent_runs.py` 확장 |
| 실행 준비·권한·snapshot·분기(`risk_signals` 포함) | `backend/app/services/agent_runs.py` 확장 |
| 실행 생성·polling·승인 API | `backend/app/api/agent_runs.py` 재사용·확장 |
| 승인 이력 모델·마이그레이션 | `backend/app/models/agent.py`(`AgentApproval`), `backend/sql/20260824_0003_agent_approval.sql` |
| Agent 단위 테스트 | `backend/tests/test_contract_management.py` 새 파일 |
| 실행·API 통합 테스트 | `backend/tests/test_agent_runs.py` 확장 |

초기 구현에서는 위험 판정, 프롬프트, 입력·출력 모델을 `app/agents/contract_management.py` 안에 둔다. 파일이 커져 서로 독립적으로 테스트할 규칙이 많아질 때만 `contract_risk.py`나 별도 schema/service로 분리한다.

> **구현 참고 (2026-08-24):** §10.2 결정에 따라 계약 데이터(`sales_deal`) 자체는 승인으로
> 반영하지 않으므로, 원래 이 표에 있던 `sales_deals.py`/`test_sales_deals.py` 확장 행은
> 제거했다. 승인은 일정관리 실행의 `POST /api/agent-runs/{agent_run_id}/approvals`
> 하나로 처리하며, 상세는 [일정관리 Agent 설계](일정관리_Agent_설계.md) §6·§11을 참고한다.

## 9. 최소 테스트

- 같은 팀의 정상 입력으로 실행 생성, 상태 전이와 output 저장
- 다른 팀 고객사·딜·보고서 접근 차단
- 승인 전 업무 테이블이 변경되지 않음
- 승인된 보고서만 입력에 포함
- 보고서가 없어도 누락 상태로 정상 완료
- 같은 중복 요청 식별키(`idempotency_key`)로 재요청할 때 실행 중복 생성 방지
- stale 대상 필드 변경 후 승인하면 `409 stale_agent_result`
- 정상 승인 시 선택된 필드만 한 트랜잭션으로 반영
- LLM 실패 시 `failed` 실행 이력 보존 및 업무 데이터 불변

## 10. 결정 사항과 남은 미확정 사항

### 10.1 위험 코드와 심각도

- **질문:** MVP에서 어떤 위험을 코드로 구분하고, 심각도는 어떤 값과 기준으로 고정할 것인가?
- **제안:** 위험 코드는 우선 `contract_expiring`, `quote_expiring`, `delivery_delay_risk`, `unresolved_support`, `follow_up_overdue`, `missing_contract_information` 여섯 개로 시작한다. 심각도는 `low`, `medium`, `high` 세 단계만 허용하고, 만료까지 남은 기간·긴급 C/S 여부·후속 조치 지연 일수처럼 DB 값으로 판정할 수 있는 기준을 코드별로 정의한다.
- **이유:** 위험 코드를 처음부터 너무 많이 만들면 화면, 알림과 테스트 조건이 복잡해진다. 최소 코드와 고정된 심각도부터 시작하면 LLM의 자유 문구에 의존하지 않고 동일한 데이터에 일관된 결과를 낼 수 있다.
- **결정 (2026-08-24):** 제안한 6개 코드를 그대로 확정하고 `ContractRisk.code`를 `Literal` enum으로
  고정했다(`backend/app/agents/contract_management.py`). 심각도 판정 기준은 새로 만들지 않고
  대시보드 팔로우업 카드(`backend/app/api/dashboard.py`)가 이미 쓰던 "기한 지남=high, 7일
  이내=medium, 그 외=위험 없음" 관례를 그대로 승계했다. `backend/app/services/agent_runs.py`의
  `_contract_source`가 딜의 `quote_valid_until`/`contract_ends_on`/`expected_delivery_at`,
  가장 임박한 `task` 활동의 `due_at`, `support_request.is_urgent`를 이 규칙으로 계산해
  `risk_signals`에 담고, LLM은 이 값을 그대로 `risks[]`에 반영하도록 프롬프트에서 지시한다.
  `missing_contract_information`은 날짜 계산 없이 파이프라인 `phase_code`가
  `contract`/`order`/`closed`인데 계약 번호·체결일·종료일 중 하나라도 비어 있으면 `low`로
  고정한다. 출력↔`risk_signals` 교차 검증(예: LLM이 신호에 없는 코드를 만들었는지 서버가
  다시 확인하는 것)은 과설계를 피하기 위해 이번 범위에 넣지 않았다 — 구조화 출력 schema와
  프롬프트 지시만으로 제어한다.

### 10.2 MVP에서 사용자가 승인할 범위

- **질문:** 사용자가 Agent 결과에서 계약 번호·계약일·종료일·단계까지 수정하고 승인하게 할 것인가, 아니면 다음 일정 제안만 승인하게 할 것인가?
- **제안:** MVP에서는 계약 정보는 조회와 위험 제안만 제공하고 자동 반영 대상에서 제외한다. 사용자는 다음 미팅 제안을 수정·승인해 일정 생성만 요청할 수 있게 한다. 계약 정보 수정은 기존 영업 딜 수정 화면과 API를 사용한다.
- **이유:** 계약 정보와 파이프라인 단계 변경은 매출 집계와 후속 업무에 직접 영향을 준다. 일정 생성부터 승인 흐름을 검증하면 잘못된 계약 정보 반영 위험을 줄이면서 Agent 실행·승인·stale·중복 요청 방지 구조를 먼저 완성할 수 있다.
- **결정 (2026-08-24):** 제안대로 계약 정보 자체는 승인·자동 반영 대상에서 계속 제외한다.
  계약관리 Agent에는 별도 승인 엔드포인트를 두지 않는다. 다만 승인 범위를 한 걸음 더
  넓혀서, 일정관리 실행의 후보 하나를 승인하는 **하나의 요청**이 (a) `activity`(+동행자) 생성과
  (b) 계약 현황 브리핑 `report`(`report_kind="contract_status_briefing"`) 생성을 함께
  수행하도록 했다. 브리핑의 `content`는 부모 `contract_management` 실행의
  `contract_summary`/`risks`/`recommended_actions`를 그대로 옮겨 담고 `status_code="draft"`로
  생성하므로, 사용자가 기존 보고서 화면에서 검토·수정한 뒤 제출할 수 있다. 구현은
  `backend/app/services/agent_runs.py`의 `approve_schedule`을 참고한다(일정관리 설계 문서
  §6 참고).

### 10.3 승인 API와 승인 이력

- **질문:** Agent 실행 결과의 승인 요청을 어느 API로 받고, 누가 무엇을 승인했는지 어디에 보관할 것인가?
- **제안:** `POST /api/agent-runs/{agent_run_id}/approvals`를 승인 요청 경로로 사용한다. 요청에는 사용자가 확정한 값과 중복 요청 식별키를 받고, 별도의 `agent_approval` 이력에 실행 ID, 요청자, 승인 값, 처리 결과, 생성된 업무 데이터 ID와 처리 시각을 기록한다. 승인 이력 저장과 실제 업무 반영은 한 트랜잭션에서 처리한다.
- **이유:** Agent 실행과 승인을 분리하면 `completed`를 승인 완료로 오해하지 않게 된다. 별도 이력을 남기면 사용자 선택값, 중복 요청, stale 거절과 실제 반영 결과를 나중에 추적할 수 있다.
- **결정 (2026-08-24):** 제안한 경로를 그대로 썼다. 다만 이 경로는 현재 `schedule_management`
  실행만 승인 대상으로 받는다(`agent_code`가 다르면 `422 approval_not_supported_for_agent`).
  `agent_approval` 테이블(`backend/app/models/agent.py`, 마이그레이션
  `backend/sql/20260824_0003_agent_approval.sql` — 파일만 작성했고 실제 DB에는 아직 적용하지
  않았다)에 `agent_run_id`, `team_id`, `requested_by_member_id`, `idempotency_key`,
  `decision_snapshot`, `result_refs`, `created_at`을 append-only로 남긴다. 같은
  `(requested_by_member_id, idempotency_key)`로 재요청하면 새로 반영하지 않고 기존 결과를
  그대로 반환한다.

### 10.4 자료요약 Agent/RAG 연동

- **질문:** 계약관리 실행 중 어느 시점에 자료를 검색하고, 자료요약 Agent에 어떤 데이터를 전달할 것인가?
- **제안:** 구조화된 DB 데이터로 기본 위험을 정리한 후, 최종 브리핑을 생성하기 직전에 RAG를 선택적으로 호출한다. 전달값은 `team_id`를 서버 내부 권한 조건으로 사용하고, 검색 조건에는 `customer_company_id`, `sales_deal_ids`, 질문 목적과 최대 문서 수만 포함한다. 계약관리 Agent에는 검색된 문서 원문 전체가 아니라 문서 ID, 관련 구간, 요약과 출처를 전달한다. 자료 검색 실패는 계약관리 실행 전체를 실패시키지 않고 자료 근거가 없는 결과로 완료한다.
- **이유:** 먼저 DB의 확정 데이터를 분석해야 검색 결과가 계약 사실을 덮어쓰지 않는다. 검색 범위와 반환량을 제한하면 다른 팀 자료 노출, 불필요한 개인정보 전달과 LLM 입력 크기 증가를 방지할 수 있다.
