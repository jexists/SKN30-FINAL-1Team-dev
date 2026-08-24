# 일정관리 Agent 설계

> 이 문서는 `schedule_management` Agent의 후보 생성, 충돌 판정과 승인 계약을 정의한다. 공통 HTTP, 인증, polling, 중복 요청 방지, 트랜잭션 규칙은 [API conventions](../backend/api-conventions.md)를 따르고, 물리 데이터 관계는 [SalesLuv ERD](../SalesLuv_ERD.md)를 기준으로 한다.

## 1. 목적과 범위

계약관리 Agent의 다음 미팅 제안과 기존 활동을 바탕으로 가능한 일정 후보와 충돌 근거를 제공한다.

- Agent는 후보를 생성할 뿐 `activity`를 자동 생성·수정·취소하지 않는다.
- `completed`는 추천 계산 완료이며 캘린더 반영 완료가 아니다.
- 실제 반영은 사용자가 후보를 수정·승인한 별도 요청에서 수행한다.
- 계약관리 Agent 출력이 없어도 직접 입력한 대상과 일정 조건으로 실행할 수 있어야 한다.

## 2. 입력과 데이터 범위

| 입력 | 필수 | 설명 |
|---|---:|---|
| `parent_run_id` | 선택 | 완료된 `contract_management` 실행 ID |
| `sales_deal_id` | 필수 | 제안 대상 딜 |
| `owner_member_id` | 필수 | 일정 담당자 |
| `preferred_date_range` | 필수 | offset을 포함한 후보 탐색 범위 |
| `duration_minutes` | 필수 | 양수인 일정 길이 |
| `companion_member_ids` | 선택 | 충돌을 함께 검사할 동행자 |
| `activity_type` | 필수 | `meeting` 또는 `task` |

조회 대상은 같은 팀의 `sales_deal`, `activity`, `activity_companion`, `activity_category`, `activity_action_tag`다. soft delete된 행은 일반 입력에서 제외한다.

## 3. Agent 실행 계약

`agent_run`에는 다음을 저장한다.

- `agent_code`: `schedule_management`
- `parent_run_id`: 입력이 계약관리 실행에서 왔을 때 해당 실행 ID
- `source_refs`: `sales_deal_id`, 충돌 검사에 사용한 `activity_ids`
- `input_snapshot`: 제안 조건과 비교 일정의 `id`, `updated_at`, 시간 필드
- `output_snapshot`: 일정 후보와 후보별 충돌 정보

```json
{
  "schedule_candidates": [
    {
      "candidate_id": "client-stable-id",
      "title": "다음 계약 협의",
      "activity_type": "meeting",
      "starts_at": "2026-08-25T14:00:00+09:00",
      "ends_at": "2026-08-25T15:00:00+09:00",
      "priority": 1,
      "reason": "string"
    }
  ],
  "conflicts": [
    {
      "activity_id": "uuid",
      "member_id": "uuid",
      "reason": "time_overlap"
    }
  ]
}
```

> **구현 참고 (2026-08-24):** `conflicts`는 후보 내부가 아니라 최상위 목록 하나로만
> 구현했고, 후보에는 대신 추천 사유를 담는 `reason` 문자열 필드를 뒀다
> (`backend/app/agents/schedule_management.py`의 `ScheduleCandidate`/`ScheduleManagementOutput`).

## 4. 권한 검증

1. 요청자, 대상 딜, 담당자와 동행자가 같은 `team_id`인지 확인한다.
2. `parent_run_id`가 있으면 같은 팀의 완료된 `contract_management` 실행인지 확인한다.
3. 대상 딜과 부모 실행의 `sales_deal_id`가 일치하는지 확인한다.
4. 일정 분류와 태그가 같은 팀의 활성 항목이며 `activity_type`과 일치하는지 확인한다.
5. 실행 조회와 승인 시 권한을 다시 검증한다.

## 5. 시간과 충돌 판정

- API 일시는 ISO 8601 offset 포함 형식으로 받고 DB에는 `timestamptz`로 저장한다.
- 화면 기본 시간대는 `Asia/Seoul`이지만 서버는 offset 없는 일시를 추측하지 않는다.
- 일반 일정은 반열린 구간 `[starts_at, ends_at)`으로 비교한다. 한 일정의 종료와 다른 일정의 시작이 같으면 충돌이 아니다.
- 담당자 또는 동행자가 겹치고 시간 구간이 겹치면 충돌이다.
- `all_day=true`는 해당 로컬 날짜 전체를 점유한다.
- `deleted_at`이 있는 활동은 충돌 대상에서 제외한다.
- 완료된 과거 활동은 후보 생성 범위와 겹치지 않으므로 자연스럽게 제외되며, 상태만으로 미래 활동을 임의 제외하지 않는다.
- `ends_at`이 필요한 일정에 값이 없으면 후보 생성 전에 요청을 거절하거나 명시된 기본 길이를 적용한다. 기본 길이는 구현 전에 정책으로 고정한다.
  **확정 (2026-08-24):** 실행 요청 schema(`AgentRunCreate`)가 `duration_minutes`를 `schedule_management` 요청의 필수값(5~480분)으로 강제하므로, 별도 기본 길이 정책은 필요 없어졌다.
- **확정 (2026-08-24):** 모든 후보의 시작·종료 시각은 `Asia/Seoul` 기준 09:00~18:00 업무시간 안에서만 제안한다. 프롬프트로만 유도하지 않고, `_within_business_hours`가 결정론적으로 재검증해 벗어난 후보는 조용히 제외한다(`backend/app/agents/schedule_management.py`). 업무 시간 밖 후보는 정책 위반일 뿐 "충돌"이 아니므로 `conflicts`에는 남기지 않는다. 주말·공휴일·이동 시간 반영 범위는 여전히 미확정이다(§11).

충돌한 후보를 제거할지 경고와 함께 반환할지는 요청 모드로 분리하지 않는 한 하나의 정책으로 고정해야 한다. MVP 권장값은 충돌 후보를 `schedule_candidates`에서 제외하고 근거를 `conflicts`에 반환하는 방식이다.
**확정 (2026-08-24):** 제안한 "제외 + 근거 반환" 방식을 그대로 채택했다. 다만 이 판정을 LLM
프롬프트 지시에만 맡기지 않고, `schedule_management.py`의 `_conflicts_for`가 반열린 구간
겹침과 `all_day`(로컬 날짜 전체 점유) 규칙으로 다시 계산해, 실제로 겹치는 후보만 제외하고
`conflicts`로 옮긴다. 승인 시점(§6)에도 같은 `_conflicts_for`를 재사용해 최종 시간을 다시
검증한다.

## 6. 승인과 실제 반영

승인 API의 구체적인 경로와 schema는 구현 시 확정하되 다음 순서를 지킨다.

1. 같은 팀의 완료된 `schedule_management` 실행인지 확인한다.
2. 사용자가 선택·수정한 최종 제목, 시간, 담당자, 동행자와 분류를 받는다.
3. 입력 스냅샷 이후 딜, 담당자와 비교 일정이 변경됐는지 확인한다.
4. 최종 시간으로 충돌을 다시 계산한다.
5. 한 DB 트랜잭션에서 `activity`와 `activity_companion`을 생성한다.
6. 생성된 활동과 원래 `agent_run`의 연결을 감사 가능한 형태로 남긴다.
7. 같은 승인 요청이 활동을 중복 생성하지 않도록 중복 요청 방지를 적용한다.

승인 요청에서 Agent가 반환한 `candidate_id`만 신뢰하지 않는다. 서버가 최종 입력 전체를 다시 검증한다.

**구현 확정 (2026-08-24):** 위 순서를 `POST /api/agent-runs/{agent_run_id}/approvals`
(`backend/app/services/agent_runs.py`의 `approve_schedule`)로 그대로 구현했다. 대상은
`schedule_management` 실행으로 한정하고(다른 `agent_code`는 `422
approval_not_supported_for_agent`), 딜 재조회 실패는 `409 stale_agent_result`, 최종 시간
겹침은 `409 schedule_conflict`로 거절한다. 5번 단계는 계약관리 §10.2 결정에 따라 한 단계
더 넓어져서, `activity`/`activity_companion` 생성과 같은 트랜잭션에서 계약 현황 브리핑
`report`(`report_kind="contract_status_briefing"`, `status_code="draft"`)도 함께 생성한다.
브리핑 내용은 부모 `contract_management` 실행(`agent_run.parent_run_id`)의 출력을 그대로
옮겨 담으며, 부모 실행이 없어도(직접 입력 시나리오) 최소 정보로 브리핑을 만든다. 6번의
"감사 가능한 연결"은 `agent_approval` 테이블의 `result_refs`(`activity_id`, `report_id`)와
`report.ai_evidence`의 `schedule_management_run_id`/`contract_management_run_id`로
구현했고, 7번의 중복 요청 방지는 `agent_approval(requested_by_member_id,
idempotency_key)` 유일 제약으로 처리한다.

## 7. stale 판정

다음 중 하나라도 해당하면 `409 stale_agent_result`를 반환하고 활동을 생성하지 않는다.

- 대상 딜이 수정·삭제되거나 담당자가 바뀜
- 입력 스냅샷에 기록한 비교 일정의 `updated_at` 또는 시간 구간이 달라짐
- 비교 일정이 삭제되었거나 새 일정이 같은 시간에 추가됨
- 부모 계약관리 실행의 대상 딜이나 제안이 현재 승인 요청과 일치하지 않음

새 일정 추가는 기존 snapshot 비교만으로 발견할 수 없으므로 승인 시 동일 시간 범위를 반드시 다시 조회한다.

## 8. 오류 계약

실행 조회, 완료 상태, stale, 중복 요청 방지, 요청 검증과 LLM 장애는 [공통 Agent 오류](../backend/api-conventions.md#141-공통-agent-오류)를 따른다. 이 Agent에는 다음 도메인 오류만 추가한다.

| 상태 | `detail` | 조건 |
|---:|---|---|
| `404` | `sales_deal_not_found` | 딜이 없거나 다른 팀 소속 |
| `404` | `member_not_found` | 담당자 또는 동행자가 없거나 다른 팀 소속 |
| `409` | `schedule_conflict` | 최종 승인 시간에 충돌이 존재함 |

## 9. 구현 파일 경로

미팅분석과 보고서작성 Agent처럼 핵심 Agent 로직만 `app/agents`에 분리하고, 실행 요청·상태 관리·polling은 기존 `agent_runs` 파일을 확장한다. 일정의 실제 생성은 Agent API가 아니라 기존 활동 리소스가 담당한다.

| 역할 | 기존 패턴에 맞춘 경로 |
|---|---|
| 핵심 Agent 로직·출력 모델·충돌/업무시간 재검증 | `backend/app/agents/schedule_management.py` 새 파일 |
| 실행·승인 요청 schema | `backend/app/schemas/agent_runs.py` 확장 |
| 실행 준비·권한·snapshot·분기, 승인 처리(`approve_schedule`) | `backend/app/services/agent_runs.py` 확장 |
| 실행 생성·polling·승인 API | `backend/app/api/agent_runs.py` 재사용·확장 |
| 승인 이력 모델·마이그레이션 | `backend/app/models/agent.py`(`AgentApproval`), `backend/sql/20260824_0003_agent_approval.sql` |
| Agent 단위 테스트 | `backend/tests/test_schedule_management.py` 새 파일 |
| 실행·API·승인 통합 테스트 | `backend/tests/test_agent_runs.py` 확장 |

초기 구현에서는 후보 생성, 충돌 판정, 프롬프트, 입력·출력 모델을 `app/agents/schedule_management.py` 안에 둔다. 충돌 판정이 복잡해져 독립적인 도메인 모듈이 필요할 때만 별도 파일로 분리한다.

> **구현 참고 (2026-08-24):** 일정 생성은 새 API를 만들지 않고 `services/agent_runs.py`의
> `approve_schedule`이 `Activity`/`ActivityCompanion`을 직접 생성하며, 분류·태그 검증은
> `app/api/activities.py`의 기존 `_active_activity_category`/`_active_activity_action_tag`를
> 그대로 재사용한다(`dashboard.py`가 다른 라우터의 헬퍼를 재사용하는 것과 같은 관례). 원래 표에
> 있던 `activities.py`/`schemas/activities.py`/`test_activities.py` 확장 행은 실제로는
> 손대지 않아 제거했다.

## 10. 최소 테스트

- 정상 입력으로 후보 생성 및 output 저장
- 계약관리 부모 실행이 없어도 직접 입력으로 실행
- 다른 팀의 딜, 담당자, 동행자와 부모 실행 접근 차단
- 경계가 맞닿은 두 일정은 충돌하지 않음
- 담당자·동행자 시간 중첩, 종일 일정과 일반 일정 충돌
- soft delete 일정 제외
- Agent 완료 전 `activity`가 생성되지 않음
- 후보 생성 후 기존 일정 수정 또는 신규 충돌 일정 생성 시 stale 거절
- 정상 승인 시 `activity`와 동행자가 한 트랜잭션으로 생성
- 중복 승인 요청이 활동을 두 번 만들지 않음

## 11. 결정 사항과 남은 미확정 사항

- ~~일정별 기본 소요 시간~~ — **확정 (2026-08-24):** `duration_minutes`가 실행 요청 필수값(5~480분)이라 별도 기본값 정책이 필요 없다. **후보 간격**(같은 요청에 여러 후보를 몇 분/시간 단위로 띄워 제안할지)은 여전히 미확정이다.
- 업무 시간, 주말·공휴일, 이동 시간 반영 범위 — **부분 확정 (2026-08-24):** 업무 시간은 `Asia/Seoul` 09:00~18:00으로 확정하고 `_within_business_hours`가 코드로 강제한다(§5). 주말·공휴일 제외 여부와 이동 시간 반영은 여전히 미확정이다.
- ~~충돌 후보를 제외할지 경고와 함께 노출할지의 최종 정책~~ — **확정 (2026-08-24):** 제외하고 근거를 `conflicts`에 남기는 방식으로 확정했다. LLM 프롬프트 지시뿐 아니라 `_conflicts_for`가 코드로 재검증한다(§5).
- ~~승인 API 경로와 Agent 실행-생성 활동 연결 방식~~ — **확정 (2026-08-24):** `POST /api/agent-runs/{agent_run_id}/approvals` + `agent_approval` 테이블로 확정했다(§6, §9). 계약관리 §10.2·§10.3 결정과 같은 흐름이다.
