# activity_action_tag

팀별 미팅 후속 조치 태그 항목을 관리

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

- **UNIQUE** `activity_action_tag_team_id_code_key` — `UNIQUE (team_id, code)`
- **CHECK** `activity_action_tag_code_check` — `CHECK ((btrim(code) <> ''::text))`
- **CHECK** `activity_action_tag_name_check` — `CHECK ((btrim(name) <> ''::text))`
- **CHECK** `activity_action_tag_position_check` — `CHECK (("position" >= 0))`
- **CHECK** `activity_action_tag_tone_check` — `CHECK ((tone = ANY (ARRAY['gray'::text, 'blue'::text, 'purple'::text, 'orange'::text, 'green'::text, 'red'::text])))`

## Indexes

- `activity_action_tag_team_position_idx` — `btree (team_id, "position") WHERE (deleted_at IS NULL)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [team](team.md) | N:1 | `activity_action_tag.team_id` → `team.id` |
| [activity](activity.md) | 1:N | `activity.activity_action_tag_id` → `activity_action_tag.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
