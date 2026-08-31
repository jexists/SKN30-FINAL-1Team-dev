# CHANGELOG

DB 구조 변경 기록.

## 기록 방법

1. 스키마를 바꾸면 `backend/sql/` 에 SQL 파일을 추가하고 Supabase 에서 적용한다.
2. 바뀐 테이블의 `tables/{테이블명}.md` 만 고친다. 바뀌지 않은 파일은 건드리지 않는다.
3. 관계(FK)가 바뀐 경우에만 [ERD.md](ERD.md) 와 [RELATIONS.md](RELATIONS.md) 를 고친다.
4. 이 문서에 날짜 → 테이블 → `ADD` / `MODIFY` / `REMOVE` 순으로 적는다.
5. [erd.html](erd.html) 안의 `SCHEMA` 데이터도 같이 고친다.

적용 여부와 실행 결과는 [`backend/sql/README.md`](../../backend/sql/README.md) 의 적용 이력 표에서 관리한다.
이 문서는 "구조가 어떻게 바뀌었는가"만 다룬다.

---

## 2026-08-31 — 문서 신설

실제 운영 DB 를 `information_schema` / `pg_catalog` 로 직접 조회해 이 폴더를 만들었다.
조회 시점 기준 **36테이블 / 379컬럼 / 외래 키 96개**.

### 실제 DB 와 저장소가 다른 부분

아래는 실제 DB 에 있지만 `develop` 의 ORM(`backend/app/models/`)과 `backend/sql/` 에는 없다.
전부 병합되지 않은 브랜치 `origin/SEONGBAE0201/document-summary-agent`(`f5d3fad`)의 SQL 이
공용 개발 DB 에 먼저 적용된 것이다. 이 폴더의 문서는 **실제 DB 기준**이라 이것들도 포함한다.

| 대상 | 내용 | 출처 SQL (미병합 브랜치) |
|---|---|---|
| `document_chunk` | 테이블 전체 (12컬럼) | `20260825_0005_document_summary.sql` |
| `document_file_audit` | 테이블 전체 (9컬럼) | `20260825_0005_document_summary.sql` |
| `file` | +10컬럼 `extracted_markdown`, `extracted_payload`, `summary_markdown`, `summary_payload`, `processing_error`, `processed_at`, `review_expires_at`, `unapproved_expires_at`, `approved_by_member_id`, `approved_at` | `20260825_0005_document_summary.sql` |
| `file` | `processing_status` CHECK 에 `review_required` 추가 | `20260825_0005_document_summary.sql` |
| `document` | +1컬럼 `customer_contact_id` (FK → `customer_contact.id`, `ON DELETE SET NULL`) + 인덱스 `document_customer_contact_idx` | `20260825_0006_business_card_archive.sql` |
| `notice` | `recipient_member_id` 가 살아 있음 + 인덱스 `notice_team_recipient_published_idx` | `20260825_0007_runtime_schema_alignment.sql` 이 되살렸고, 다시 떼는 `20260825_0008_notice_schema_alignment.sql` 은 이 DB 에 적용되지 않았다 |

`develop` 의 [`backend/tests/test_models.py`](../../backend/tests/test_models.py) 는 ORM 기준인
34테이블 / 346컬럼을 확인한다. 위 항목들은 그 검사 범위 밖이다.

`backend/sql/20260831_0014_report_legacy_deal_scope.sql` 은 아직 적용되지 않았지만 DDL 이 없는
데이터 보정이라 구조에는 영향이 없다.

### 이전 이력 (backend/sql 기준)

| 날짜 | 파일 | 구조 변경 |
|---|---|---|
| 2026-08-19 | `0001_baseline_schema` | 26테이블 신설. 전 테이블 RLS ON |
| 2026-08-23 | `0002_admin_account_provisioning` | `team` ADD `company_name`·`department`·`business_no` / `member` ADD `email` |
| 2026-08-24 | `0003_customer_contact_assignees` | `customer_contact_assignee` 신설 / `customer_contact` ADD `created_by_member_id` / `customer_company` ADD `business_no` |
| 2026-08-24 | `0004_customer_contact_visited` | `customer_contact` ADD `visited` |
| 2026-08-24 | `0004_product_fields` | `product` ADD `category_code`·`unit_price`·`shelf_life_months`·`memo`·`image_storage_key` |
| 2026-08-25 | `0005_one_manager_per_team` | `member` 부분 유일 인덱스 `member_one_manager_per_team_uq` |
| 2026-08-25 | `0005_notice_management` | `notice_target`·`notice_image` 신설 / `notice` ADD `type`·`display_start_date`·`display_end_date`·`is_hidden`·`sort_order`·`updated_at`·`deleted_at`, REMOVE `recipient_member_id` |
| 2026-08-25 | `0006_support_request_deal_link` | `support_request` ADD `customer_company_id`·`sales_deal_id`·`occurred_at`, REMOVE `customer_contact_id`, 복합 FK 신설 / `sales_deal` ADD UNIQUE `(id, customer_company_id)` |
| 2026-08-26 | `0007_deal_quote_contract_order` | `quote_status`·`contract_status`·`sales_deal_item`·`sales_deal_participant` 신설 / `sales_deal` ADD `quote_status_id`·`contract_status_id`·`quote_amount`·`contract_amount`·`quote_delivery_terms` / `purchase_order` ADD `request_department`·`cooperation_department`·`created_by_member_id`·`expected_customer_company_id` |
| 2026-08-26 | `0008_contract_terms` | `sales_deal` ADD `contract_payment_terms`·`contract_late_interest_terms` |
| 2026-08-26 | `0009_customer_company_address` | `customer_company` ADD `postcode`·`address`·`address_detail` |
| 적용 시점 미상 | `0011_sales_deal_source` | `sales_deal` ADD `source_code` |
| 적용 시점 미상 | `0012_document_product_link` | `document` ADD `product_id` |
| 2026-08-28 | `0013_report_sales_deal` | `report` ADD `sales_deal_id` + 부분 유일 인덱스 |
| 2026-08-28 | `0010_drop_activity_type` | `activity`·`activity_category`·`activity_action_tag` REMOVE `activity_type` |
| 2026-08-29 | `0013_contract_next_meeting_suggestion` | `contract_next_meeting_suggestion` 신설 |

`0013_report_sales_deal` 이 `0010_drop_activity_type` 보다 먼저 적용되어 파일 번호와 적용 순서가 다르다.

---

[← 전체 테이블 목록](README.md)
