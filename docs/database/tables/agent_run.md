# agent_run

AI 에이전트 실행의 입출력과 근거를 남기는 감사 로그

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `parent_run_id` | UUID | FK → agent_run.id | YES | – | 이 실행을 부른 상위 실행 ID |
| `requested_by_member_id` | UUID | FK → member.id | YES | – | 실행을 요청한 구성원 ID |
| `agent_code` | TEXT | – | NO | – | 실행한 에이전트 코드 |
| `trigger_code` | TEXT | – | NO | – | 실행을 일으킨 트리거 코드 |
| `idempotency_key` | UUID | – | YES | – | 중복 실행 방지 키 |
| `status_code` | TEXT | – | NO | – | 실행 상태 (queued / running / completed / failed) |
| `llm_model_name` | TEXT | – | NO | – | 사용한 LLM 모델 이름 |
| `prompt_version` | TEXT | – | NO | – | 사용한 프롬프트 버전 |
| `source_refs` | JSONB | – | NO | – | 입력이 참조한 레코드 목록 |
| `input_snapshot` | JSONB | – | NO | – | 실행 시점 입력 스냅샷 |
| `output_snapshot` | JSONB | – | YES | – | 실행 결과 출력 |
| `evidence` | JSONB | – | YES | – | 결과의 근거 정보 |
| `error_message` | TEXT | – | YES | – | 실패 사유 |
| `started_at` | TIMESTAMPTZ | – | YES | – | 실행 시작 시각 |
| `finished_at` | TIMESTAMPTZ | – | YES | – | 실행 종료 시각 |

## Constraints

- **UNIQUE** `agent_run_requested_by_member_id_idempotency_key_key` — `UNIQUE (requested_by_member_id, idempotency_key)`
- **CHECK** `agent_run_agent_code_check` — `CHECK ((btrim(agent_code) <> ''::text))`
- **CHECK** `agent_run_error_message_check` — `CHECK (((error_message IS NULL) OR (btrim(error_message) <> ''::text)))`
- **CHECK** `agent_run_idempotency_requester` — `CHECK (((idempotency_key IS NULL) OR (requested_by_member_id IS NOT NULL)))`
- **CHECK** `agent_run_llm_model_name_check` — `CHECK ((btrim(llm_model_name) <> ''::text))`
- **CHECK** `agent_run_not_own_parent` — `CHECK (((parent_run_id IS NULL) OR (parent_run_id <> id)))`
- **CHECK** `agent_run_prompt_version_check` — `CHECK ((btrim(prompt_version) <> ''::text))`
- **CHECK** `agent_run_status_code_check` — `CHECK ((status_code = ANY (ARRAY['queued'::text, 'running'::text, 'completed'::text, 'failed'::text])))`
- **CHECK** `agent_run_trigger_code_check` — `CHECK ((btrim(trigger_code) <> ''::text))`

## Indexes

- `agent_run_parent_idx` — `btree (parent_run_id) WHERE (parent_run_id IS NOT NULL)`
- `agent_run_team_status_idx` — `btree (team_id, status_code)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [agent_run](agent_run.md) | N:1 | `agent_run.parent_run_id` → `agent_run.id` |
| [member](member.md) | N:1 | `agent_run.requested_by_member_id` → `member.id` |
| [team](team.md) | N:1 | `agent_run.team_id` → `team.id` |
| [agent_run](agent_run.md) | 1:N | `agent_run.parent_run_id` → `agent_run.id` |
| [contract_next_meeting_suggestion](contract_next_meeting_suggestion.md) | 1:N | `contract_next_meeting_suggestion.schedule_management_run_id` → `agent_run.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
