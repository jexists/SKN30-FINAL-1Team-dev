# Relations

실제 DB 에 걸린 외래 키 **96개** 전부. 컬럼 설명은 `tables/{테이블명}.md` 에 있다.

관계 타입은 자식 테이블 기준이다. 자식의 FK 컬럼이 유니크하면 `1:1`, 아니면 `N:1` 이다.

## 전체 목록

| 자식 | 자식 컬럼 | 부모 | 부모 컬럼 | 관계 | ON DELETE / ON UPDATE | 제약 이름 |
|---|---|---|---|---|---|---|
| [activity](tables/activity.md) | `activity_action_tag_id` | [activity_action_tag](tables/activity_action_tag.md) | `id` | N:1 | – | `activity_activity_action_tag_id_fkey` |
| [activity](tables/activity.md) | `activity_category_id` | [activity_category](tables/activity_category.md) | `id` | N:1 | – | `activity_activity_category_id_fkey` |
| [activity](tables/activity.md) | `customer_contact_id` | [customer_contact](tables/customer_contact.md) | `id` | N:1 | – | `activity_customer_contact_id_fkey` |
| [activity](tables/activity.md) | `end_user_contact_id` | [customer_contact](tables/customer_contact.md) | `id` | N:1 | – | `activity_end_user_contact_id_fkey` |
| [activity](tables/activity.md) | `owner_member_id` | [member](tables/member.md) | `id` | N:1 | – | `activity_owner_member_id_fkey` |
| [activity](tables/activity.md) | `product_id` | [product](tables/product.md) | `id` | N:1 | – | `activity_product_id_fkey` |
| [activity](tables/activity.md) | `purchase_order_id` | [purchase_order](tables/purchase_order.md) | `id` | N:1 | – | `activity_purchase_order_id_fkey` |
| [activity](tables/activity.md) | `sales_deal_id` | [sales_deal](tables/sales_deal.md) | `id` | N:1 | – | `activity_sales_deal_id_fkey` |
| [activity](tables/activity.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `activity_team_id_fkey` |
| [activity_action_tag](tables/activity_action_tag.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `activity_action_tag_team_id_fkey` |
| [activity_category](tables/activity_category.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `activity_category_team_id_fkey` |
| [activity_companion](tables/activity_companion.md) | `activity_id` | [activity](tables/activity.md) | `id` | N:1 | CASCADE | `activity_companion_activity_id_fkey` |
| [activity_companion](tables/activity_companion.md) | `member_id` | [member](tables/member.md) | `id` | N:1 | – | `activity_companion_member_id_fkey` |
| [agent_run](tables/agent_run.md) | `parent_run_id` | [agent_run](tables/agent_run.md) | `id` | N:1 | – | `agent_run_parent_run_id_fkey` |
| [agent_run](tables/agent_run.md) | `requested_by_member_id` | [member](tables/member.md) | `id` | N:1 | – | `agent_run_requested_by_member_id_fkey` |
| [agent_run](tables/agent_run.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `agent_run_team_id_fkey` |
| [contract_next_meeting_suggestion](tables/contract_next_meeting_suggestion.md) | `schedule_management_run_id` | [agent_run](tables/agent_run.md) | `id` | N:1 | – | `contract_next_meeting_suggestio_schedule_management_run_id_fkey` |
| [contract_next_meeting_suggestion](tables/contract_next_meeting_suggestion.md) | `sales_deal_id` | [sales_deal](tables/sales_deal.md) | `id` | 1:1 | – | `contract_next_meeting_suggestion_sales_deal_id_fkey` |
| [contract_next_meeting_suggestion](tables/contract_next_meeting_suggestion.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `contract_next_meeting_suggestion_team_id_fkey` |
| [contract_status](tables/contract_status.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `contract_status_team_id_fkey` |
| [customer_company](tables/customer_company.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `customer_company_team_id_fkey` |
| [customer_contact](tables/customer_contact.md) | `company_id` | [customer_company](tables/customer_company.md) | `id` | N:1 | – | `customer_contact_company_id_fkey` |
| [customer_contact](tables/customer_contact.md) | `created_by_member_id` | [member](tables/member.md) | `id` | N:1 | – | `customer_contact_created_by_member_id_fkey` |
| [customer_contact](tables/customer_contact.md) | `customer_contact_status_id` | [customer_contact_status](tables/customer_contact_status.md) | `id` | N:1 | – | `customer_contact_customer_contact_status_id_fkey` |
| [customer_contact](tables/customer_contact.md) | `owner_member_id` | [member](tables/member.md) | `id` | N:1 | – | `customer_contact_owner_member_id_fkey` |
| [customer_contact_assignee](tables/customer_contact_assignee.md) | `customer_contact_id` | [customer_contact](tables/customer_contact.md) | `id` | N:1 | CASCADE | `customer_contact_assignee_customer_contact_id_fkey` |
| [customer_contact_assignee](tables/customer_contact_assignee.md) | `member_id` | [member](tables/member.md) | `id` | N:1 | – | `customer_contact_assignee_member_id_fkey` |
| [customer_contact_status](tables/customer_contact_status.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `customer_contact_status_team_id_fkey` |
| [document](tables/document.md) | `created_by_member_id` | [member](tables/member.md) | `id` | N:1 | – | `document_created_by_member_id_fkey` |
| [document](tables/document.md) | `customer_company_id` | [customer_company](tables/customer_company.md) | `id` | N:1 | – | `document_customer_company_id_fkey` |
| [document](tables/document.md) | `customer_contact_id` | [customer_contact](tables/customer_contact.md) | `id` | N:1 | SET NULL | `document_customer_contact_id_fkey` |
| [document](tables/document.md) | `product_id` | [product](tables/product.md) | `id` | N:1 | – | `document_product_id_fkey` |
| [document](tables/document.md) | `purchase_order_id` | [purchase_order](tables/purchase_order.md) | `id` | N:1 | – | `document_purchase_order_id_fkey` |
| [document](tables/document.md) | `sales_deal_id` | [sales_deal](tables/sales_deal.md) | `id` | N:1 | – | `document_sales_deal_id_fkey` |
| [document](tables/document.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `document_team_id_fkey` |
| [document_chunk](tables/document_chunk.md) | `document_id` | [document](tables/document.md) | `id` | N:1 | CASCADE | `document_chunk_document_id_fkey` |
| [document_chunk](tables/document_chunk.md) | `file_id` | [file](tables/file.md) | `id` | N:1 | CASCADE | `document_chunk_file_id_fkey` |
| [document_chunk](tables/document_chunk.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `document_chunk_team_id_fkey` |
| [document_file_audit](tables/document_file_audit.md) | `actor_member_id` | [member](tables/member.md) | `id` | N:1 | – | `document_file_audit_actor_member_id_fkey` |
| [document_file_audit](tables/document_file_audit.md) | `document_id` | [document](tables/document.md) | `id` | N:1 | CASCADE | `document_file_audit_document_id_fkey` |
| [document_file_audit](tables/document_file_audit.md) | `file_id` | [file](tables/file.md) | `id` | N:1 | CASCADE | `document_file_audit_file_id_fkey` |
| [document_file_audit](tables/document_file_audit.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `document_file_audit_team_id_fkey` |
| [file](tables/file.md) | `approved_by_member_id` | [member](tables/member.md) | `id` | N:1 | – | `file_approved_by_member_id_fkey` |
| [file](tables/file.md) | `document_id` | [document](tables/document.md) | `id` | N:1 | – | `file_document_id_fkey` |
| [file](tables/file.md) | `report_id` | [report](tables/report.md) | `id` | N:1 | – | `file_report_id_fkey` |
| [file](tables/file.md) | `uploaded_by_member_id` | [member](tables/member.md) | `id` | N:1 | – | `file_uploaded_by_member_id_fkey` |
| [member](tables/member.md) | `id` | `auth.users` | `id` | 1:1 | – | `member_id_fkey` |
| [member](tables/member.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `member_team_id_fkey` |
| [notice](tables/notice.md) | `author_member_id` | [member](tables/member.md) | `id` | N:1 | – | `notice_author_member_id_fkey` |
| [notice](tables/notice.md) | `recipient_member_id` | [member](tables/member.md) | `id` | N:1 | – | `notice_recipient_member_id_fkey` |
| [notice](tables/notice.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `notice_team_id_fkey` |
| [notice_image](tables/notice_image.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `notice_image_team_id_fkey` |
| [notice_image](tables/notice_image.md) | `uploaded_by_member_id` | [member](tables/member.md) | `id` | N:1 | – | `notice_image_uploaded_by_member_id_fkey` |
| [notice_target](tables/notice_target.md) | `member_id` | [member](tables/member.md) | `id` | N:1 | – | `notice_target_member_id_fkey` |
| [notice_target](tables/notice_target.md) | `notice_id` | [notice](tables/notice.md) | `id` | N:1 | CASCADE | `notice_target_notice_id_fkey` |
| [product](tables/product.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `product_team_id_fkey` |
| [purchase_order](tables/purchase_order.md) | `created_by_member_id` | [member](tables/member.md) | `id` | N:1 | – | `purchase_order_created_by_member_id_fkey` |
| [purchase_order](tables/purchase_order.md) | `expected_customer_company_id` | [customer_company](tables/customer_company.md) | `id` | N:1 | – | `purchase_order_expected_customer_company_id_fkey` |
| [purchase_order](tables/purchase_order.md) | `purchase_order_status_id` | [purchase_order_status](tables/purchase_order_status.md) | `id` | N:1 | – | `purchase_order_purchase_order_status_id_fkey` |
| [purchase_order](tables/purchase_order.md) | `sales_deal_id` | [sales_deal](tables/sales_deal.md) | `id` | N:1 | – | `purchase_order_sales_deal_id_fkey` |
| [purchase_order](tables/purchase_order.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `purchase_order_team_id_fkey` |
| [purchase_order_item](tables/purchase_order_item.md) | `product_id` | [product](tables/product.md) | `id` | N:1 | – | `purchase_order_item_product_id_fkey` |
| [purchase_order_item](tables/purchase_order_item.md) | `purchase_order_id` | [purchase_order](tables/purchase_order.md) | `id` | N:1 | CASCADE | `purchase_order_item_purchase_order_id_fkey` |
| [purchase_order_status](tables/purchase_order_status.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `purchase_order_status_team_id_fkey` |
| [quote_status](tables/quote_status.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `quote_status_team_id_fkey` |
| [report](tables/report.md) | `author_member_id` | [member](tables/member.md) | `id` | N:1 | – | `report_author_member_id_fkey` |
| [report](tables/report.md) | `recipient_member_id` | [member](tables/member.md) | `id` | N:1 | – | `report_recipient_member_id_fkey` |
| [report](tables/report.md) | `reviewed_by_member_id` | [member](tables/member.md) | `id` | N:1 | – | `report_reviewed_by_member_id_fkey` |
| [report](tables/report.md) | `sales_deal_id` | [sales_deal](tables/sales_deal.md) | `id` | N:1 | – | `report_sales_deal_id_fkey` |
| [report](tables/report.md) | `source_activity_id` | [activity](tables/activity.md) | `id` | N:1 | – | `report_source_activity_id_fkey` |
| [report](tables/report.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `report_team_id_fkey` |
| [report_activity](tables/report_activity.md) | `activity_id` | [activity](tables/activity.md) | `id` | N:1 | – | `report_activity_activity_id_fkey` |
| [report_activity](tables/report_activity.md) | `report_id` | [report](tables/report.md) | `id` | N:1 | CASCADE | `report_activity_report_id_fkey` |
| [sales_deal](tables/sales_deal.md) | `contract_status_id` | [contract_status](tables/contract_status.md) | `id` | N:1 | – | `sales_deal_contract_status_id_fkey` |
| [sales_deal](tables/sales_deal.md) | `customer_company_id` | [customer_company](tables/customer_company.md) | `id` | N:1 | – | `sales_deal_customer_company_id_fkey` |
| [sales_deal](tables/sales_deal.md) | `customer_contact_id` | [customer_contact](tables/customer_contact.md) | `id` | N:1 | – | `sales_deal_customer_contact_id_fkey` |
| [sales_deal](tables/sales_deal.md) | `owner_member_id` | [member](tables/member.md) | `id` | N:1 | – | `sales_deal_owner_member_id_fkey` |
| [sales_deal](tables/sales_deal.md) | `product_id` | [product](tables/product.md) | `id` | N:1 | – | `sales_deal_product_id_fkey` |
| [sales_deal](tables/sales_deal.md) | `quote_status_id` | [quote_status](tables/quote_status.md) | `id` | N:1 | – | `sales_deal_quote_status_id_fkey` |
| [sales_deal](tables/sales_deal.md) | `sales_deal_type_id` | [sales_deal_type](tables/sales_deal_type.md) | `id` | N:1 | – | `sales_deal_sales_deal_type_id_fkey` |
| [sales_deal](tables/sales_deal.md) | `sales_pipeline_id, sales_pipeline_stage_id` | [sales_pipeline_stage](tables/sales_pipeline_stage.md) | `sales_pipeline_id, id` | N:1 | – | `sales_deal_sales_pipeline_stage_membership_fkey` |
| [sales_deal](tables/sales_deal.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `sales_deal_team_id_fkey` |
| [sales_deal_item](tables/sales_deal_item.md) | `product_id` | [product](tables/product.md) | `id` | N:1 | – | `sales_deal_item_product_id_fkey` |
| [sales_deal_item](tables/sales_deal_item.md) | `sales_deal_id` | [sales_deal](tables/sales_deal.md) | `id` | N:1 | CASCADE | `sales_deal_item_sales_deal_id_fkey` |
| [sales_deal_participant](tables/sales_deal_participant.md) | `customer_contact_id` | [customer_contact](tables/customer_contact.md) | `id` | N:1 | – | `sales_deal_participant_customer_contact_id_fkey` |
| [sales_deal_participant](tables/sales_deal_participant.md) | `sales_deal_id` | [sales_deal](tables/sales_deal.md) | `id` | N:1 | CASCADE | `sales_deal_participant_sales_deal_id_fkey` |
| [sales_deal_type](tables/sales_deal_type.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `sales_deal_type_team_id_fkey` |
| [sales_pipeline](tables/sales_pipeline.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `sales_pipeline_team_id_fkey` |
| [sales_pipeline_stage](tables/sales_pipeline_stage.md) | `sales_pipeline_id` | [sales_pipeline](tables/sales_pipeline.md) | `id` | N:1 | – | `sales_pipeline_stage_sales_pipeline_id_fkey` |
| [sales_target](tables/sales_target.md) | `customer_company_id` | [customer_company](tables/customer_company.md) | `id` | N:1 | – | `sales_target_customer_company_id_fkey` |
| [sales_target](tables/sales_target.md) | `owner_member_id` | [member](tables/member.md) | `id` | N:1 | – | `sales_target_owner_member_id_fkey` |
| [support_request](tables/support_request.md) | `assignee_member_id` | [member](tables/member.md) | `id` | N:1 | – | `support_request_assignee_member_id_fkey` |
| [support_request](tables/support_request.md) | `sales_deal_id, customer_company_id` | [sales_deal](tables/sales_deal.md) | `id, customer_company_id` | N:1 | CASCADE | `support_request_sales_deal_company_membership_fkey` |
| [support_request](tables/support_request.md) | `team_id` | [team](tables/team.md) | `id` | N:1 | – | `support_request_team_id_fkey` |
| [support_response](tables/support_response.md) | `responder_member_id` | [member](tables/member.md) | `id` | N:1 | – | `support_response_responder_member_id_fkey` |
| [support_response](tables/support_response.md) | `support_request_id` | [support_request](tables/support_request.md) | `id` | N:1 | – | `support_response_support_request_id_fkey` |

## N:M 연결 테이블

복합 기본 키로 두 테이블을 잇는다. `secondary=` 를 쓰는 ORM 관계는 없고 모두 독립 모델이다.

| 연결 테이블 | 양쪽 | 기본 키 |
|---|---|---|
| [notice_target](tables/notice_target.md) | `notice` ↔ `member` | `member_id, notice_id` |
| [customer_contact_assignee](tables/customer_contact_assignee.md) | `customer_contact` ↔ `member` | `customer_contact_id, member_id` |
| [activity_companion](tables/activity_companion.md) | `activity` ↔ `member` | `activity_id, member_id` |
| [report_activity](tables/report_activity.md) | `report` ↔ `activity` | `activity_id, report_id` |
| [sales_deal_participant](tables/sales_deal_participant.md) | `sales_deal` ↔ `customer_contact` | `customer_contact_id, sales_deal_id` |

## 복합 외래 키

두 컬럼을 묶어 참조해서, 자식 행이 부모의 특정 조합에서만 나올 수 있게 한다.

### `sales_deal_sales_pipeline_stage_membership_fkey`

- `sales_deal (sales_pipeline_id, sales_pipeline_stage_id)` → `sales_pipeline_stage (sales_pipeline_id, id)`
- ON DELETE / ON UPDATE: 없음

### `support_request_sales_deal_company_membership_fkey`

- `support_request (sales_deal_id, customer_company_id)` → `sales_deal (id, customer_company_id)`
- ON DELETE / ON UPDATE: CASCADE

## 자기 참조

- `agent_run.parent_run_id` → `agent_run.id` (`agent_run_parent_run_id_fkey`)

## 같은 테이블을 두 번 이상 참조

| 자식 | 부모 | 컬럼 |
|---|---|---|
| `activity` | `customer_contact` | `customer_contact_id`, `end_user_contact_id` |
| `customer_contact` | `member` | `created_by_member_id`, `owner_member_id` |
| `file` | `member` | `approved_by_member_id`, `uploaded_by_member_id` |
| `notice` | `member` | `author_member_id`, `recipient_member_id` |
| `report` | `member` | `author_member_id`, `recipient_member_id`, `reviewed_by_member_id` |

## 외부 스키마 참조

- `member.id` → `auth.users.id` (`member_id_fkey`) — Supabase Auth 계정

---

[← 전체 테이블 목록](README.md) · [Interactive ERD](erd.html)
