# customer_contact_status

팀별 고객 담당자 상태 표시 항목을 관리

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

## Constraints

- **UNIQUE** `customer_contact_status_team_id_code_key` — `UNIQUE (team_id, code)`
- **CHECK** `customer_contact_status_code_check` — `CHECK ((btrim(code) <> ''::text))`
- **CHECK** `customer_contact_status_name_check` — `CHECK ((btrim(name) <> ''::text))`
- **CHECK** `customer_contact_status_position_check` — `CHECK (("position" >= 0))`
- **CHECK** `customer_contact_status_tone_check` — `CHECK ((tone = ANY (ARRAY['gray'::text, 'blue'::text, 'purple'::text, 'orange'::text, 'green'::text, 'red'::text])))`

## Indexes

- `customer_contact_status_team_position_idx` — `btree (team_id, "position") WHERE (deleted_at IS NULL)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [team](team.md) | N:1 | `customer_contact_status.team_id` → `team.id` |
| [customer_contact](customer_contact.md) | 1:N | `customer_contact.customer_contact_status_id` → `customer_contact_status.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
