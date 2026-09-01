# contract_next_meeting_suggestion

거래별 AI 다음 미팅 제안의 현재 상태를 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `sales_deal_id` | UUID | FK → sales_deal.id, UNIQUE | NO | – | 제안 대상 거래 ID (거래당 1건) |
| `schedule_management_run_id` | UUID | FK → agent_run.id | NO | – | 제안 내용을 담은 일정관리 실행 ID |
| `status_code` | TEXT | – | NO | – | 제안 처리 상태 (pending / dismissed / accepted) |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 생성 시각 |
| `updated_at` | TIMESTAMPTZ | – | NO | `now()` | 수정 시각 |

## Constraints

- **CHECK** `contract_next_meeting_suggestion_status_code_check` — `CHECK ((status_code = ANY (ARRAY['pending'::text, 'dismissed'::text, 'accepted'::text])))`

## Indexes

- `contract_next_meeting_suggestion_team_status_idx` — `btree (team_id, status_code)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [agent_run](agent_run.md) | N:1 | `contract_next_meeting_suggestion.schedule_management_run_id` → `agent_run.id` |
| [sales_deal](sales_deal.md) | 1:1 | `contract_next_meeting_suggestion.sales_deal_id` → `sales_deal.id` |
| [team](team.md) | N:1 | `contract_next_meeting_suggestion.team_id` → `team.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
