# purchase_order_status

팀별 발주 상태 표시 항목을 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `code` | TEXT | – | NO | – | 팀 안에서 항목을 구분하는 코드 |
| `name` | TEXT | – | NO | – | 표시 이름 |
| `tone` | TEXT | – | NO | – | 표시 색상 |
| `position` | INTEGER | – | NO | – | 정렬 순서 |
| `deleted_at` | TIMESTAMPTZ | – | YES | – | 삭제 시각 (NULL 이면 사용 중) |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 생성 시각 |
| `updated_at` | TIMESTAMPTZ | – | NO | `now()` | 수정 시각 |
| `outcome_code` | TEXT | – | NO | – | 상태가 뜻하는 결과 구분 |

## Constraints

- **UNIQUE** `purchase_order_status_team_id_code_key` — `UNIQUE (team_id, code)`
- **CHECK** `purchase_order_status_code_check` — `CHECK ((btrim(code) <> ''::text))`
- **CHECK** `purchase_order_status_name_check` — `CHECK ((btrim(name) <> ''::text))`
- **CHECK** `purchase_order_status_outcome_code_check` — `CHECK ((outcome_code = ANY (ARRAY['in_progress'::text, 'completed'::text, 'cancelled'::text])))`
- **CHECK** `purchase_order_status_position_check` — `CHECK (("position" >= 0))`
- **CHECK** `purchase_order_status_tone_check` — `CHECK ((tone = ANY (ARRAY['gray'::text, 'blue'::text, 'purple'::text, 'orange'::text, 'green'::text, 'red'::text])))`

## Indexes

- `purchase_order_status_team_position_idx` — `btree (team_id, "position") WHERE (deleted_at IS NULL)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [team](team.md) | N:1 | `purchase_order_status.team_id` → `team.id` |
| [purchase_order](purchase_order.md) | 1:N | `purchase_order.purchase_order_status_id` → `purchase_order_status.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
