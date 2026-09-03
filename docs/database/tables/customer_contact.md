# customer_contact

고객 회사에 소속된 담당자 정보를 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `company_id` | UUID | FK → customer_company.id | NO | – | 소속 고객사 ID |
| `owner_member_id` | UUID | FK → member.id | NO | – | 주담당 구성원 ID |
| `name` | TEXT | – | NO | – | 담당자 이름 |
| `department` | TEXT | – | YES | – | 담당자 부서 |
| `job_title` | TEXT | – | YES | – | 담당자 직함 |
| `email` | TEXT | – | YES | – | 담당자 이메일 |
| `phone` | TEXT | – | NO | – | 담당자 연락처 |
| `source_code` | TEXT | – | YES | – | 유입 경로 코드 |
| `memo` | TEXT | – | YES | – | 메모 |
| `registered_at` | TIMESTAMPTZ | – | NO | `now()` | 등록 시각 |
| `customer_contact_status_id` | UUID | FK → customer_contact_status.id | YES | – | 담당자 상태 ID |
| `created_by_member_id` | UUID | FK → member.id | NO | – | 등록한 구성원 ID (등록 후 변경 없음) |
| `visited` | BOOLEAN | – | NO | `false` | 방문 여부 (수동 표시) |
| `deleted_at` | TIMESTAMPTZ | – | YES | – | 삭제 시각 (팀장 전용 소프트 삭제). NULL이면 살아 있는 고객 |

## Constraints

- **CHECK** `customer_contact_department_check` — `CHECK (((department IS NULL) OR (btrim(department) <> ''::text)))`
- **CHECK** `customer_contact_email_check` — `CHECK (((email IS NULL) OR (btrim(email) <> ''::text)))`
- **CHECK** `customer_contact_job_title_check` — `CHECK (((job_title IS NULL) OR (btrim(job_title) <> ''::text)))`
- **CHECK** `customer_contact_memo_check` — `CHECK (((memo IS NULL) OR (btrim(memo) <> ''::text)))`
- **CHECK** `customer_contact_name_check` — `CHECK ((btrim(name) <> ''::text))`
- **CHECK** `customer_contact_phone_check` — `CHECK ((btrim(phone) <> ''::text))`
- **CHECK** `customer_contact_source_code_check` — `CHECK (((source_code IS NULL) OR (btrim(source_code) <> ''::text)))`

## Indexes

- `customer_contact_company_name_idx` — `btree (company_id, name)`
- `customer_contact_owner_idx` — `btree (owner_member_id)`
- `customer_contact_active_idx` — `btree (id) WHERE deleted_at IS NULL`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [customer_company](customer_company.md) | N:1 | `customer_contact.company_id` → `customer_company.id` |
| [member](member.md) | N:1 | `customer_contact.created_by_member_id` → `member.id` |
| [customer_contact_status](customer_contact_status.md) | N:1 | `customer_contact.customer_contact_status_id` → `customer_contact_status.id` |
| [member](member.md) | N:1 | `customer_contact.owner_member_id` → `member.id` |
| [activity](activity.md) | 1:N | `activity.customer_contact_id` → `customer_contact.id` |
| [activity](activity.md) | 1:N | `activity.end_user_contact_id` → `customer_contact.id` |
| [customer_contact_assignee](customer_contact_assignee.md) | 1:N | `customer_contact_assignee.customer_contact_id` → `customer_contact.id` |
| [document](document.md) | 1:N | `document.customer_contact_id` → `customer_contact.id` |
| [sales_deal](sales_deal.md) | 1:N | `sales_deal.customer_contact_id` → `customer_contact.id` |
| [sales_deal_participant](sales_deal_participant.md) | 1:N | `sales_deal_participant.customer_contact_id` → `customer_contact.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
