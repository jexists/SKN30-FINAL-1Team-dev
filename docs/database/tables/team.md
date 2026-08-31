# team

CRM 을 사용하는 영업 조직 단위이자 모든 데이터의 소속 기준

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `name` | TEXT | – | NO | – | 팀 이름 |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 생성 시각 |
| `company_name` | TEXT | – | YES | – | 회사 이름 |
| `department` | TEXT | – | YES | – | 부서 이름 |
| `business_no` | TEXT | – | YES | – | 사업자등록번호 (하이픈 없는 10자리) |

## Constraints

- **CHECK** `team_business_no_check` — `CHECK (((business_no IS NULL) OR (business_no ~ '^[0-9]{10}$'::text)))`
- **CHECK** `team_company_name_check` — `CHECK (((company_name IS NULL) OR (btrim(company_name) <> ''::text)))`
- **CHECK** `team_department_check` — `CHECK (((department IS NULL) OR (btrim(department) <> ''::text)))`
- **CHECK** `team_name_check` — `CHECK ((btrim(name) <> ''::text))`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [activity](activity.md) | 1:N | `activity.team_id` → `team.id` |
| [activity_action_tag](activity_action_tag.md) | 1:N | `activity_action_tag.team_id` → `team.id` |
| [activity_category](activity_category.md) | 1:N | `activity_category.team_id` → `team.id` |
| [agent_run](agent_run.md) | 1:N | `agent_run.team_id` → `team.id` |
| [contract_next_meeting_suggestion](contract_next_meeting_suggestion.md) | 1:N | `contract_next_meeting_suggestion.team_id` → `team.id` |
| [contract_status](contract_status.md) | 1:N | `contract_status.team_id` → `team.id` |
| [customer_company](customer_company.md) | 1:N | `customer_company.team_id` → `team.id` |
| [customer_contact_status](customer_contact_status.md) | 1:N | `customer_contact_status.team_id` → `team.id` |
| [document](document.md) | 1:N | `document.team_id` → `team.id` |
| [document_chunk](document_chunk.md) | 1:N | `document_chunk.team_id` → `team.id` |
| [document_file_audit](document_file_audit.md) | 1:N | `document_file_audit.team_id` → `team.id` |
| [member](member.md) | 1:N | `member.team_id` → `team.id` |
| [notice](notice.md) | 1:N | `notice.team_id` → `team.id` |
| [notice_image](notice_image.md) | 1:N | `notice_image.team_id` → `team.id` |
| [product](product.md) | 1:N | `product.team_id` → `team.id` |
| [purchase_order](purchase_order.md) | 1:N | `purchase_order.team_id` → `team.id` |
| [purchase_order_status](purchase_order_status.md) | 1:N | `purchase_order_status.team_id` → `team.id` |
| [quote_status](quote_status.md) | 1:N | `quote_status.team_id` → `team.id` |
| [report](report.md) | 1:N | `report.team_id` → `team.id` |
| [sales_deal](sales_deal.md) | 1:N | `sales_deal.team_id` → `team.id` |
| [sales_deal_type](sales_deal_type.md) | 1:N | `sales_deal_type.team_id` → `team.id` |
| [sales_pipeline](sales_pipeline.md) | 1:N | `sales_pipeline.team_id` → `team.id` |
| [support_request](support_request.md) | 1:N | `support_request.team_id` → `team.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
