# 미팅분석 → 보고서작성 → 계약관리 → 일정관리 Agent 흐름

> 이 문서는 미팅분석·보고서작성·계약관리·일정관리 4개 Agent가 실제로 어떻게 동작하는지, 개발자와 Agent(코딩 에이전트)가 순서대로 따라가며 읽을 수 있도록 코드 기준으로 정리한 것이다. 자료요약(RAG) Agent는 아직 구현되지 않아 계약관리 Agent의 브리핑 입력에서 항상 빈 값으로 들어간다.
>
> 계약관리·일정관리 Agent의 정확한 Input/Output/상태 정의는 [계약에이전트_설계.md](계약에이전트_설계.md)와 [일정관리에이전트_설계.md](일정관리에이전트_설계.md)를 기준으로 삼는다. 이 문서와 그 두 문서가 어긋나면 두 설계 문서가 맞다 — 이 문서는 4개 Agent를 한 흐름으로 훑어보는 용도다.

## 전체 흐름

```text
미팅 원문(녹음/메모/직접입력)
  → [미팅분석] 딜 특성 구조화 + 계약가능성 분류
  → [보고서작성] 보고서 초안 생성 → 작성자가 수정·확정
  → (확정이 트리거) [계약관리 1차] 위험 판정 + 다음 미팅 제안
  → [일정관리] 겹치지 않는 일정 후보 추천
  → contract_next_meeting_suggestion 에 저장
  → 사람이 캘린더에서 보고 최종 승인 → 캘린더/DB에 일정 등록
  → [계약관리 재진입] 등록된 일정 + RAG 자료로 브리핑 생성
```

미팅분석과 보고서작성은 같은 draft 보고서(`report_id`)를 각자 독립적으로 입력받아 실행되는
두 개의 별개 실행이다 — 한쪽 출력이 다른 쪽 입력으로 직접 이어지지 않는다(아래 2번 참고).
계약관리 1차→일정관리는 `agent_runs`의 `parent_run_id`로 이어지고, **서버가 백그라운드에서
자동으로 잇는다**(`backend/app/services/contract_next_meeting_pipeline.py`). 클라이언트가
단계를 순서대로 호출하지 않는다 — 캘린더는 저장된 결과를 조회만 한다. 일정관리→재진입
(브리핑)도 마찬가지로, 사용자가 승인한 일정을 `POST /activities`로 등록할 때
`schedule_management_run_id`를 같이 보내면 서버가 등록 커밋 직후 브리핑 실행까지 자동으로
이어서 큐잉한다.

파이프라인을 시작시키는 트리거는 네 가지다: **보고서 확정**(`POST /reports/{id}/submit`),
**일정 수동 등록**, **영업 딜 생성·단계 이동**, **CS 처리 시작**(→`in_progress`). 넷 모두
영업 건 하나를 정확히 가리키므로 여러 딜을 비교·랭킹하는 0차 선별은 이 경로에 없다.

## 단계별 설명

### 1. 미팅분석 Agent — 미팅 원문에서 계약가능성 분류 입력을 뽑는다

- **구현**: `backend/app/agents/meeting_analysis.py`, `agent_code="meeting_analysis"`
- **Input**: draft 보고서의 `transcript`(미팅 원문 텍스트)
- **처리**: LLM이 원문에서 10개 딜 특성(Authority·Competitors·Purch_dept·Budgt_alloc·Forml_tend·RFI·RFP·Posit_statm·Scope·Needs_def)을 구조화한다. 원문에 없으면 추측하지 않고 `Unknown`으로 둔다. 이 10개 특성을 별도 ML 모델(`app/ml/deal_baseline.py`)에 넣어 `계약가능성 높음(high)` / `계약가능성 주의(watch)`와 확률을 계산한다.
- **Output**: `deal_assessment`(구조화된 10개 특성 + `label` + `high_probability` + `model_version`). C/S 사항 추출은 이 Agent의 출력에 없다.
- **다음 단계 연결**: 없다. 이 출력은 보고서작성 Agent나 계약관리 Agent로 자동으로 넘어가지 않고, 화면에 참고 지표로만 표시하는 용도다.

### 2. 보고서작성 Agent — 보고서 양식의 초안을 채우고, 사람이 승인해야 완성된다

- **구현**: `backend/app/agents/report_writing.py`, `agent_code="report_writing"`
- **Input**: 같은 draft 보고서의 양식(`template_snapshot`)·현재 작성값(`content`)·미팅 원문(`transcript`, 있으면)·작성자 요청(`guidance`, 있으면). 미팅분석 Agent의 출력(`deal_assessment`)은 입력으로 받지 않는다 — 둘 다 같은 `report_id`를 보고 각자 실행될 뿐, 한쪽 결과가 다른 쪽으로 전달되는 파이프는 없다.
- **처리**: 양식의 각 입력칸(`field_id`)에 채울 값을 만든다. 근거가 없는 칸은 빈 문자열로 둔다.
- **사람 확인 지점**: 작성자가 초안을 수정하고 "확정"을 눌러야(`POST /reports/{id}/submit`, 상태 `submitted`) 완성으로 취급된다. **`draft` 상태의 보고서는 계약관리 Agent 입력에 들어가지 않는다** — 계약관리 1차 제안은 `status_code`가 `submitted` 이거나 `approved`인 보고서만 다시 조회해서 쓴다(`backend/app/services/contract_schedule_snapshots.py`의 `_recent_finalized_reports`). 이 확정이 곧 계약관리 파이프라인의 트리거이기도 하다.
- **Output**: 확정된 보고서(`submitted` 또는 `approved`) → (DB에 저장된 상태로) 계약관리 Agent가 나중에 다시 조회하는 자료가 된다. Agent 출력이 직접 계약관리 Agent를 호출하는 구조는 아니다.

### 3. 계약관리 Agent 0차 — 제안 대상 딜을 선별한다 (캘린더 경로에서는 쓰지 않는다)

- **구현**: `backend/app/agents/contract_management.py`의 `select_next_meeting_candidates()`, `agent_code="contract_management_select_candidates"`
- **Input**: 로그인한 담당자가 소유한, 아직 끝나지 않은 모든 딜의 위험 신호. 위험 신호(계약 만료·견적 만료·납품 지연·미해결 C/S·장기 미접촉·계약 정보 누락)는 결정적 규칙으로 미리 계산하고(`contract_schedule_snapshots.build_candidate_selection_snapshot`), 신호가 하나도 없는 딜은 입력에도 넣지 않는다.
- **처리**: 위험이 여러 개 겹치거나 심각도가 높거나 마감이 임박한 딜을 LLM이 우선순위로 선별한다. 이 단계는 대상을 지정할 필요가 없다 — 요청에 `customer_company_id` 등 식별자를 넣으면 오히려 거부된다.
- **Output**: 지금 보여줄 딜 목록(최대 10개), 각각 회사·딜 ID와 선택 이유·우선순위(`priority`, 1이 가장 시급).
- **어디에 쓰이나**: 캘린더 패널은 트리거 기반 선계산으로 바뀌면서 이 단계를 거치지 않는다. `POST /agent-runs`로는 여전히 실행할 수 있고, 기존 딜을 한 번에 채우는 백필 스크립트(`backend/scripts/backfill_contract_next_meeting_suggestions.py`)가 대상을 고를 때 같은 규칙(`build_candidate_selection_snapshot`)을 쓴다.

### 4. 계약관리 Agent 1차 — 선별된 딜의 위험을 판정하고 다음 미팅을 제안한다

- **구현**: `contract_management.py`의 `propose_next_meeting()`, `agent_code="contract_management_next_meeting"`
- **Input**: 특정 회사(`customer_company_id`, 트리거가 가리킨 딜의 고객사)의 고객사 정보, 열린 딜 요약, 위험 신호, 최근 확정된 보고서 5건(`submitted` 또는 `approved`)
- **처리**: 위험을 판정하고, 필요하면 다음 미팅의 이유·선호 기간·소요 시간을 제안한다. 입력에 날짜 근거가 없으면 날짜를 지어내지 않는다. 브리핑 문장은 만들지 않는다.
- **Output**: `risks`, `missing_information`, `recommended_actions`, `next_meeting_suggestion`(있으면) → 다음 단계(일정관리)의 입력 재료가 된다.

### 5. 일정관리 Agent — 겹치지 않는 일정 후보를 추천한다

- **구현**: `backend/app/agents/schedule_management.py`의 `run()`, `agent_code="schedule_management"`
- **Input**: 영업 건 ID, 선호 기간·소요 시간·이유(1차 실행을 `parent_run_id`로 이어받거나, 없으면 요청에서 직접 지정), 담당 영업사원의 기존 일정
- **처리**: Asia/Seoul 09:00~18:00 업무시간 안에서 기존 일정과 겹치지 않는 후보를 만든다. LLM 출력은 서버가 다시 검증해 업무시간 밖이거나 실제로 겹치는 후보를 걸러낸다.
- **Output**: 일정 후보 목록(최대 10개, `priority`는 1이 가장 추천), 충돌 정보
- **계약관리 Agent와의 교류**: 없다. 충돌하는 후보는 그냥 버리고 `conflicts`로만 보고할 뿐, 계약관리 Agent에 대체 후보를 요청·응답하는 왕복 호출은 구현돼 있지 않다. 이 교류는 [일정관리에이전트_설계.md](일정관리에이전트_설계.md)의 "향후 확장 계획"에만 있는 구상이다.

### 6. 계약관리 Agent 재진입 — 승인된 일정과 자료요약을 묶어 브리핑을 만든다

- **구현**: `contract_management.py`의 `generate_briefing()`, `agent_code="contract_management_briefing"`
- **Input**: 사용자가 승인해 등록된 일정(`activity_id`), 고객사·딜 현황, 자료요약(RAG) — 자료요약 Agent가 아직 없어 이 값은 항상 빈 배열이다.
- **처리**: 승인된 일정과 계약·딜 현황을 근거로 브리핑을 요약한다. 근거가 없는 항목은 채우지 않고 `missing_information`에 남긴다.
- **Output**: `contract_summary`, `source_refs`, `risks`, `missing_information`, `recommended_actions`
- **주의**: 일정 등록(`POST /activities`)에 `schedule_management_run_id`(완료된 일정관리 실행 ID)를 실어 보내면, 서버가 등록 커밋 직후 같은 요청 안에서 이 실행을 자동으로 큐잉한다 — 클라이언트가 `agent-runs`를 별도로 다시 호출할 필요는 없다. 큐잉 자체가 실패하면(부모 실행을 못 찾음 등) 일정 등록은 그대로 두고 응답의 `briefing_queue_warning`으로만 알린다.

## 설계 원칙: 이전 단계 데이터가 없어도 동작해야 한다

각 Agent는 앞 단계의 출력이 아직 없어도 최소한으로는 동작한다.

- 확정된 보고서가 없으면 → 계약관리 1차 제안은 계약 활동(위험 신호)만으로 위험 판정을 만들고, 보고서 근거가 필요한 항목은 `missing_information`으로 비워 둔다.
- 계약관리 1차 제안이 없으면 → 일정관리 Agent는 요청에 직접 넣은 선호 시간대만으로 동작한다(`parent_run_id` 없이 호출 가능).
- 자료요약(RAG) 결과가 없으면 → 브리핑은 그래도 만들되, 문서 근거가 필요한 항목은 `missing_information`으로 비워 둔다.

이 원칙에 따라 계약관리·일정관리 Agent의 대상 식별 필드(`customer_company_id`, `activity_id`, `parent_run_id` 등)는 모두 optional/조건부로 설계돼 있고, 값이 없을 때의 동작이 테스트로 확인돼 있다(`backend/tests/test_contract_management.py`, `test_schedule_management.py`, `test_agent_runs.py`).

## 사람 확인이 필요한 지점 (Human-in-the-loop)

| Agent | 지점 | 확인 전에는 |
|---|---|---|
| 보고서작성 | 초안 → 수정·확정(`submitted`) | 계약관리 1차 제안의 "최근 확정된 보고서" 입력에 들어가지 않음. 확정 자체가 파이프라인 트리거이기도 함 |
| 계약관리 1차/일정관리 | 다음 미팅 제안 → 일정 후보 → 사용자 최종 승인 | 계약·일정을 자동으로 바꾸지 않음(제안만) |
| 계약관리 재진입 | 브리핑 생성 | 일정 등록이 성공하기 전에는 만들지 않음 |

포트폴리오 선별(0차)은 승인 게이트가 아니라 "지금 무엇을 보여줄지" 고르는 필터라, 사람이 확인·승인하는 지점은 아니다. 캘린더 경로에서는 이 단계 자체가 빠졌다(3번 참고).

## 현재 구현 상태

- 4개 Agent 모두 백엔드 구현과 실 LLM 연동이 끝났다: 미팅분석, 보고서작성, 계약관리(0차/1차/재진입 3개 실행), 일정관리 (`backend/app/agents/`)
- Agent 오케스트레이션은 `backend/app/services/agent_runs.py`(사용자 요청 경로)와 `backend/app/services/contract_next_meeting_pipeline.py`(트리거 기반 선계산 경로)가 나눠 맡는다. 선계산 경로는 계약관리 1차→일정관리를 서버가 백그라운드로 자동으로 잇고, 결과를 `contract_next_meeting_suggestion`에 저장한다. 일정관리→계약관리 재진입(브리핑)은 `backend/app/api/activities.py`의 `create_activity`가 `schedule_management_run_id`를 받아 자동으로 이어서 큐잉한다.
- 같은 딜에 트리거가 몰려도 10분 안에는 다시 돌리지 않는다(`_COOLDOWN`). 진행 중인 실행이 있으면 시각과 무관하게 막는다.
- 미팅분석 ↔ 보고서작성은 서로 연결돼 있지 않다. 계약관리 1차 제안도 보고서작성 Agent의 출력을 직접 받지 않고, DB에서 확정된(`submitted`/`approved`) 보고서를 다시 조회하는 방식으로만 간접 연결된다.
- 자료요약(RAG) Agent: 미구현. 브리핑 입력의 `document_summaries`는 항상 빈 배열이다.
- 프론트엔드: 미팅 상세(`RecordDrawer`)가 브리핑 결과를 읽기 전용으로 보여주고, 캘린더 탭의 "AI 추천 일정" 패널(`SuggestionPanel`)이 저장된 제안을 조회해 보여주고 승인받는다. 패널은 LLM을 직접 호출하지 않는다 — `GET /contract-next-meeting-suggestions` 한 번이 전부다.
- 트리거가 한 번도 걸리지 않은 기존 딜은 제안이 없어 패널에 뜨지 않는다. `backend/scripts/backfill_contract_next_meeting_suggestions.py`로 한 번에 채운다.

## 참고 문서

- [계약에이전트_설계.md](계약에이전트_설계.md) — 계약관리 Agent(0차/1차/재진입)의 정확한 설계
- [일정관리에이전트_설계.md](일정관리에이전트_설계.md) — 일정관리 Agent의 정확한 설계와 향후 확장 계획
- [계약에이전트_테스트.md](계약에이전트_테스트.md) — 위 두 Agent의 테스트 방법과 결과
- [SalesLuv_ERD.md](../SalesLuv_ERD.md) — 데이터 모델
- [딜_승산_점수_데이터_전처리_및_AI_학습_모델.md](../딜_승산_점수_데이터_전처리_및_AI_학습_모델.md) — 미팅분석 Agent가 쓰는 ML 모델
