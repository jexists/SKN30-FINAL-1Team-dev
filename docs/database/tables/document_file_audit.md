# document_file_audit

자료 파일의 업로드와 요약 승인 이력을 기록

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `document_id` | UUID | FK → document.id | NO | – | 대상 자료 ID |
| `file_id` | UUID | FK → file.id | NO | – | 대상 파일 ID |
| `action_code` | TEXT | – | NO | – | 기록한 동작 (file_uploaded / summary_reprocess_requested / summary_approved) |
| `actor_member_id` | UUID | FK → member.id | NO | – | 동작을 수행한 구성원 ID |
| `before_snapshot` | JSONB | – | YES | – | 동작 전 상태 스냅샷 |
| `after_snapshot` | JSONB | – | YES | – | 동작 후 상태 스냅샷 |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 생성 시각 |

## Constraints

- **CHECK** `document_file_audit_action_code_check` — `CHECK ((action_code = ANY (ARRAY['file_uploaded'::text, 'summary_reprocess_requested'::text, 'summary_approved'::text])))`

## Indexes

- `document_file_audit_file_created_idx` — `btree (file_id, created_at DESC)`
- `document_file_audit_team_created_idx` — `btree (team_id, created_at DESC)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [member](member.md) | N:1 | `document_file_audit.actor_member_id` → `member.id` |
| [document](document.md) | N:1 | `document_file_audit.document_id` → `document.id` |
| [file](file.md) | N:1 | `document_file_audit.file_id` → `file.id` |
| [team](team.md) | N:1 | `document_file_audit.team_id` → `team.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
