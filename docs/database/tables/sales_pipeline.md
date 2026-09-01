# sales_pipeline

팀이 사용하는 영업 파이프라인 버전을 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `name` | TEXT | – | NO | – | 파이프라인 이름 |
| `description` | TEXT | – | YES | – | 설명 |
| `status_code` | TEXT | – | NO | – | 게시 상태 (draft / published / archived) |
| `is_default` | BOOLEAN | – | NO | `false` | 팀 기본 파이프라인 여부 |
| `published_at` | TIMESTAMPTZ | – | YES | – | 게시 시각 |
| `archived_at` | TIMESTAMPTZ | – | YES | – | 보관 시각 |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 생성 시각 |
| `updated_at` | TIMESTAMPTZ | – | NO | `now()` | 수정 시각 |

## Constraints

- **UNIQUE** `sales_pipeline_team_id_name_key` — `UNIQUE (team_id, name)`
- **CHECK** `sales_pipeline_default_check` — `CHECK (((NOT is_default) OR (status_code = 'published'::text)))`
- **CHECK** `sales_pipeline_description_check` — `CHECK (((description IS NULL) OR (btrim(description) <> ''::text)))`
- **CHECK** `sales_pipeline_lifecycle_check` — `CHECK ((((status_code = 'draft'::text) AND (published_at IS NULL) AND (archived_at IS NULL)) OR ((status_code = 'published'::text) AND (published_at IS NOT NULL) AND (archived_at IS NULL)) OR ((status_code = 'archived'::text) AND (published_at IS NOT NULL) AND (archived_at IS NOT NULL) AND (archived_at >= published_at))))`
- **CHECK** `sales_pipeline_name_check` — `CHECK ((btrim(name) <> ''::text))`
- **CHECK** `sales_pipeline_status_code_check` — `CHECK ((status_code = ANY (ARRAY['draft'::text, 'published'::text, 'archived'::text])))`

## Indexes

- `sales_pipeline_team_published_default_uq` — `btree (team_id) WHERE (is_default AND (status_code = 'published'::text))`
- `sales_pipeline_team_status_idx` — `btree (team_id, status_code, created_at DESC)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [team](team.md) | N:1 | `sales_pipeline.team_id` → `team.id` |
| [sales_pipeline_stage](sales_pipeline_stage.md) | 1:N | `sales_pipeline_stage.sales_pipeline_id` → `sales_pipeline.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
