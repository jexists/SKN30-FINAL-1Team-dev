# report

미팅·업무 보고서의 본문과 검토 상태를 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `author_member_id` | UUID | FK → member.id | NO | – | 작성한 구성원 ID |
| `recipient_member_id` | UUID | FK → member.id | YES | – | 보고 대상 구성원 ID |
| `template_snapshot` | JSONB | – | NO | – | 작성 시점 보고서 서식 스냅샷 |
| `source_activity_id` | UUID | FK → activity.id | YES | – | 보고서의 근거 미팅 일정 ID |
| `report_kind` | TEXT | – | NO | – | 보고서 종류 |
| `report_date` | DATE | – | NO | – | 보고 기준일 |
| `period_start` | DATE | – | YES | – | 보고 기간 시작일 |
| `period_end` | DATE | – | YES | – | 보고 기간 종료일 |
| `status_code` | TEXT | – | NO | – | 작성·검토 상태 |
| `content` | JSONB | – | NO | – | 보고서 본문 (서식 필드별 값) |
| `transcript` | TEXT | – | YES | – | 미팅 녹취 원문 |
| `source_snapshot` | JSONB | – | YES | – | AI 입력에 쓴 원본 데이터 스냅샷 |
| `ai_evidence` | JSONB | – | YES | – | AI 초안의 근거 정보 |
| `note` | TEXT | – | YES | – | 작성자 비고 |
| `reviewed_by_member_id` | UUID | FK → member.id | YES | – | 검토한 구성원 ID |
| `reviewed_at` | TIMESTAMPTZ | – | YES | – | 검토 시각 |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 생성 시각 |
| `updated_at` | TIMESTAMPTZ | – | NO | `now()` | 수정 시각 |
| `sales_deal_id` | UUID | FK → sales_deal.id | YES | – | 보고서가 다루는 거래 ID |

## Constraints

- **CHECK** `report_note_check` — `CHECK (((note IS NULL) OR (btrim(note) <> ''::text)))`
- **CHECK** `report_period_order` — `CHECK (((period_start IS NULL) OR (period_end IS NULL) OR (period_end >= period_start)))`
- **CHECK** `report_report_kind_check` — `CHECK ((btrim(report_kind) <> ''::text))`
- **CHECK** `report_status_code_check` — `CHECK ((btrim(status_code) <> ''::text))`
- **CHECK** `report_transcript_check` — `CHECK (((transcript IS NULL) OR (btrim(transcript) <> ''::text)))`

## Indexes

- `report_sales_deal_date_idx` — `btree (sales_deal_id, report_date DESC) WHERE (sales_deal_id IS NOT NULL)`
- `report_source_activity_idx` — `btree (source_activity_id) WHERE (source_activity_id IS NOT NULL)`
- `report_source_activity_sales_deal_key` — `btree (source_activity_id, sales_deal_id) WHERE ((source_activity_id IS NOT NULL) AND (sales_deal_id IS NOT NULL))`
- `report_team_author_date_idx` — `btree (team_id, author_member_id, report_date DESC)`
- `report_team_status_idx` — `btree (team_id, status_code)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [member](member.md) | N:1 | `report.author_member_id` → `member.id` |
| [member](member.md) | N:1 | `report.recipient_member_id` → `member.id` |
| [member](member.md) | N:1 | `report.reviewed_by_member_id` → `member.id` |
| [sales_deal](sales_deal.md) | N:1 | `report.sales_deal_id` → `sales_deal.id` |
| [activity](activity.md) | N:1 | `report.source_activity_id` → `activity.id` |
| [team](team.md) | N:1 | `report.team_id` → `team.id` |
| [file](file.md) | 1:N | `file.report_id` → `report.id` |
| [report_activity](report_activity.md) | 1:N | `report_activity.report_id` → `report.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
