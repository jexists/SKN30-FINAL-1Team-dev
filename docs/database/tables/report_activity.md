# report_activity

보고서가 다루는 미팅 일정을 연결

> `report` 와 `activity` 를 잇는 N:M 연결 테이블. 두 컬럼이 복합 기본 키다.

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `report_id` | UUID | PK, FK → report.id | NO | – | 보고서 ID |
| `activity_id` | UUID | PK, FK → activity.id | NO | – | 포함된 미팅 일정 ID |

## Indexes

- `report_activity_activity_idx` — `btree (activity_id)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [activity](activity.md) | N:1 | `report_activity.activity_id` → `activity.id` |
| [report](report.md) | N:1 | `report_activity.report_id` → `report.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
