# sales_deal_type

팀별 거래 유형 표시 항목을 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `code` | TEXT | – | NO | – | 팀 안에서 항목을 구분하는 코드 |
| `name` | TEXT | – | NO | – | 표시 이름 |
| `position` | INTEGER | – | NO | – | 정렬 순서 |
| `deleted_at` | TIMESTAMPTZ | – | YES | – | 삭제 시각 (NULL 이면 사용 중) |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 생성 시각 |
| `updated_at` | TIMESTAMPTZ | – | NO | `now()` | 수정 시각 |

## Constraints

- **UNIQUE** `sales_deal_type_team_id_code_key` — `UNIQUE (team_id, code)`
- **CHECK** `sales_deal_type_code_check` — `CHECK ((btrim(code) <> ''::text))`
- **CHECK** `sales_deal_type_name_check` — `CHECK ((btrim(name) <> ''::text))`
- **CHECK** `sales_deal_type_position_check` — `CHECK (("position" >= 0))`

## Indexes

- `sales_deal_type_team_position_idx` — `btree (team_id, "position") WHERE (deleted_at IS NULL)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [team](team.md) | N:1 | `sales_deal_type.team_id` → `team.id` |
| [sales_deal](sales_deal.md) | 1:N | `sales_deal.sales_deal_type_id` → `sales_deal_type.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
