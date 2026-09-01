# sales_pipeline_stage

파이프라인을 구성하는 단계와 순서를 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `name` | TEXT | – | NO | – | 단계 이름 |
| `tone` | TEXT | – | NO | – | 표시 색상 |
| `outcome_code` | TEXT | – | NO | – | 단계가 뜻하는 결과 (in_progress / confirmed / cancelled) |
| `position` | INTEGER | – | NO | – | 파이프라인 안 단계 순서 |
| `sales_pipeline_id` | UUID | FK → sales_pipeline.id | NO | – | 파이프라인 ID |
| `stage_code` | TEXT | – | NO | – | 단계 코드 |
| `phase_code` | TEXT | – | NO | – | 단계가 속한 국면 (sales / quote / contract / order / closed) |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 생성 시각 |
| `updated_at` | TIMESTAMPTZ | – | NO | `now()` | 수정 시각 |

## Constraints

- **UNIQUE** `sales_pipeline_stage_sales_pipeline_id_id_key` — `UNIQUE (sales_pipeline_id, id)`
- **UNIQUE** `sales_pipeline_stage_sales_pipeline_id_position_key` — `UNIQUE (sales_pipeline_id, "position")`
- **UNIQUE** `sales_pipeline_stage_sales_pipeline_id_stage_code_key` — `UNIQUE (sales_pipeline_id, stage_code)`
- **CHECK** `sales_pipeline_stage_name_check` — `CHECK ((btrim(name) <> ''::text))`
- **CHECK** `sales_pipeline_stage_outcome_code_check` — `CHECK ((outcome_code = ANY (ARRAY['in_progress'::text, 'confirmed'::text, 'cancelled'::text])))`
- **CHECK** `sales_pipeline_stage_phase_code_check` — `CHECK ((phase_code = ANY (ARRAY['sales'::text, 'quote'::text, 'contract'::text, 'order'::text, 'closed'::text])))`
- **CHECK** `sales_pipeline_stage_position_check` — `CHECK (("position" >= 0))`
- **CHECK** `sales_pipeline_stage_stage_code_check` — `CHECK ((btrim(stage_code) <> ''::text))`
- **CHECK** `sales_pipeline_stage_tone_check` — `CHECK ((tone = ANY (ARRAY['gray'::text, 'blue'::text, 'purple'::text, 'orange'::text, 'green'::text, 'red'::text])))`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [sales_pipeline](sales_pipeline.md) | N:1 | `sales_pipeline_stage.sales_pipeline_id` → `sales_pipeline.id` |
| [sales_deal](sales_deal.md) | 1:N | `sales_deal.sales_pipeline_id, sales_deal.sales_pipeline_stage_id` → `sales_pipeline_stage.sales_pipeline_id, sales_pipeline_stage.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
