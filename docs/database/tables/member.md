# member

서비스에 등록된 내부 사용자와 소속 팀·권한을 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK, FK → auth.users.id | NO | – | 사용자 ID (Supabase auth.users.id 와 같은 값) |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `display_name` | TEXT | – | NO | – | 사용자 이름 |
| `role_code` | TEXT | – | NO | – | 사용자 권한 (member / manager) |
| `job_title` | TEXT | – | YES | – | 직함 |
| `active` | BOOLEAN | – | NO | `true` | 재직 여부 |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 생성 시각 |
| `email` | TEXT | – | YES | – | 로그인 이메일 |

## Constraints

- **CHECK** `member_display_name_check` — `CHECK ((btrim(display_name) <> ''::text))`
- **CHECK** `member_email_check` — `CHECK (((email IS NULL) OR (btrim(email) <> ''::text)))`
- **CHECK** `member_job_title_check` — `CHECK (((job_title IS NULL) OR (btrim(job_title) <> ''::text)))`
- **CHECK** `member_role_code_check` — `CHECK ((role_code = ANY (ARRAY['member'::text, 'manager'::text])))`

## Indexes

- `member_email_uq` — `btree (lower(email)) WHERE (email IS NOT NULL)`
- `member_team_active_idx` — `btree (team_id, active)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| `auth.users` | 1:1 | `member.id` → `auth.users.id` |
| [team](team.md) | N:1 | `member.team_id` → `team.id` |
| [activity](activity.md) | 1:N | `activity.owner_member_id` → `member.id` |
| [activity_companion](activity_companion.md) | 1:N | `activity_companion.member_id` → `member.id` |
| [agent_run](agent_run.md) | 1:N | `agent_run.requested_by_member_id` → `member.id` |
| [customer_contact](customer_contact.md) | 1:N | `customer_contact.created_by_member_id` → `member.id` |
| [customer_contact](customer_contact.md) | 1:N | `customer_contact.owner_member_id` → `member.id` |
| [customer_contact_assignee](customer_contact_assignee.md) | 1:N | `customer_contact_assignee.member_id` → `member.id` |
| [document](document.md) | 1:N | `document.created_by_member_id` → `member.id` |
| [document_file_audit](document_file_audit.md) | 1:N | `document_file_audit.actor_member_id` → `member.id` |
| [file](file.md) | 1:N | `file.approved_by_member_id` → `member.id` |
| [file](file.md) | 1:N | `file.uploaded_by_member_id` → `member.id` |
| [notice](notice.md) | 1:N | `notice.author_member_id` → `member.id` |
| [notice](notice.md) | 1:N | `notice.recipient_member_id` → `member.id` |
| [notice_image](notice_image.md) | 1:N | `notice_image.uploaded_by_member_id` → `member.id` |
| [notice_target](notice_target.md) | 1:N | `notice_target.member_id` → `member.id` |
| [purchase_order](purchase_order.md) | 1:N | `purchase_order.created_by_member_id` → `member.id` |
| [report](report.md) | 1:N | `report.author_member_id` → `member.id` |
| [report](report.md) | 1:N | `report.recipient_member_id` → `member.id` |
| [report](report.md) | 1:N | `report.reviewed_by_member_id` → `member.id` |
| [sales_deal](sales_deal.md) | 1:N | `sales_deal.owner_member_id` → `member.id` |
| [sales_target](sales_target.md) | 1:N | `sales_target.owner_member_id` → `member.id` |
| [support_request](support_request.md) | 1:N | `support_request.assignee_member_id` → `member.id` |
| [support_response](support_response.md) | 1:N | `support_response.responder_member_id` → `member.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
