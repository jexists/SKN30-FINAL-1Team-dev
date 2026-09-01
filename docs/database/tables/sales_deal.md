# sales_deal

고객사와 진행하는 영업 거래와 견적·계약 정보를 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `deal_no` | TEXT | – | NO | – | 거래 번호 |
| `customer_company_id` | UUID | FK → customer_company.id | NO | – | 고객사 ID |
| `customer_contact_id` | UUID | FK → customer_contact.id | YES | – | 주 고객 담당자 ID |
| `owner_member_id` | UUID | FK → member.id | NO | – | 담당 구성원 ID |
| `product_id` | UUID | FK → product.id | YES | – | 대표 제품 ID |
| `sales_pipeline_stage_id` | UUID | FK → sales_pipeline_stage (복합 FK) | NO | – | 현재 단계 ID |
| `title` | TEXT | – | NO | – | 거래 제목 |
| `description` | TEXT | – | YES | – | 설명 |
| `deal_amount` | BIGINT | – | NO | – | 거래 예상 금액 (원) |
| `opened_on` | DATE | – | NO | – | 거래 시작일 |
| `contract_ends_on` | DATE | – | YES | – | 계약 종료일 |
| `warranty_terms` | TEXT | – | YES | – | 보증 조건 |
| `expected_delivery_at` | TIMESTAMPTZ | – | YES | – | 납품 예정 시각 |
| `memo` | TEXT | – | YES | – | 메모 |
| `stage_position` | INTEGER | – | NO | – | 단계 안 카드 정렬 순서 |
| `deleted_at` | TIMESTAMPTZ | – | YES | – | 삭제 시각 (NULL 이면 사용 중) |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 생성 시각 |
| `updated_at` | TIMESTAMPTZ | – | NO | `now()` | 수정 시각 |
| `sales_pipeline_id` | UUID | FK → sales_pipeline_stage (복합 FK) | NO | – | 적용 파이프라인 ID |
| `sales_deal_type_id` | UUID | FK → sales_deal_type.id | NO | – | 거래 유형 ID |
| `closed_on` | DATE | – | YES | – | 거래 종료일 |
| `quote_no` | TEXT | – | YES | – | 견적 번호 |
| `quote_issued_on` | DATE | – | YES | – | 견적 발행일 |
| `quote_valid_until` | DATE | – | YES | – | 견적 유효 기한 |
| `contract_no` | TEXT | – | YES | – | 계약 번호 |
| `contract_signed_on` | DATE | – | YES | – | 계약 체결일 |
| `quote_status_id` | UUID | FK → quote_status.id | YES | – | 견적 상태 ID (NULL 이면 견적 미진입) |
| `contract_status_id` | UUID | FK → contract_status.id | YES | – | 계약 상태 ID (NULL 이면 계약 미진입) |
| `quote_amount` | BIGINT | – | YES | – | 견적 금액 (원) |
| `contract_amount` | BIGINT | – | YES | – | 계약 금액 (원) |
| `quote_delivery_terms` | TEXT | – | YES | – | 견적 납품 조건 |
| `contract_payment_terms` | TEXT | – | YES | – | 물품 대금 지급 기일 |
| `contract_late_interest_terms` | TEXT | – | YES | – | 대금 연체 이자율 조건 |
| `source_code` | TEXT | – | YES | – | 거래 유입 경로 코드 |

## Constraints

- **UNIQUE** `sales_deal_id_customer_company_key` — `UNIQUE (id, customer_company_id)`
- **UNIQUE** `sales_deal_team_id_contract_no_key` — `UNIQUE (team_id, contract_no)`
- **UNIQUE** `sales_deal_team_id_deal_no_key` — `UNIQUE (team_id, deal_no)`
- **UNIQUE** `sales_deal_team_id_quote_no_key` — `UNIQUE (team_id, quote_no)`
- **CHECK** `sales_deal_closed_on_order_check` — `CHECK (((closed_on IS NULL) OR (closed_on >= opened_on)))`
- **CHECK** `sales_deal_contract_amount_check` — `CHECK (((contract_amount IS NULL) OR (contract_amount >= 0)))`
- **CHECK** `sales_deal_contract_ends_on_order_check` — `CHECK (((contract_ends_on IS NULL) OR ((contract_signed_on IS NOT NULL) AND (contract_ends_on >= contract_signed_on))))`
- **CHECK** `sales_deal_contract_late_interest_terms_check` — `CHECK (((contract_late_interest_terms IS NULL) OR (btrim(contract_late_interest_terms) <> ''::text)))`
- **CHECK** `sales_deal_contract_no_check` — `CHECK (((contract_no IS NULL) OR (btrim(contract_no) <> ''::text)))`
- **CHECK** `sales_deal_contract_payment_terms_check` — `CHECK (((contract_payment_terms IS NULL) OR (btrim(contract_payment_terms) <> ''::text)))`
- **CHECK** `sales_deal_contract_signed_on_check` — `CHECK (((contract_signed_on IS NULL) OR (contract_signed_on >= opened_on)))`
- **CHECK** `sales_deal_deal_amount_check` — `CHECK ((deal_amount >= 0))`
- **CHECK** `sales_deal_deal_no_check` — `CHECK ((btrim(deal_no) <> ''::text))`
- **CHECK** `sales_deal_description_check` — `CHECK (((description IS NULL) OR (btrim(description) <> ''::text)))`
- **CHECK** `sales_deal_memo_check` — `CHECK (((memo IS NULL) OR (btrim(memo) <> ''::text)))`
- **CHECK** `sales_deal_quote_amount_check` — `CHECK (((quote_amount IS NULL) OR (quote_amount >= 0)))`
- **CHECK** `sales_deal_quote_delivery_terms_check` — `CHECK (((quote_delivery_terms IS NULL) OR (btrim(quote_delivery_terms) <> ''::text)))`
- **CHECK** `sales_deal_quote_issued_on_check` — `CHECK (((quote_issued_on IS NULL) OR (quote_issued_on >= opened_on)))`
- **CHECK** `sales_deal_quote_no_check` — `CHECK (((quote_no IS NULL) OR (btrim(quote_no) <> ''::text)))`
- **CHECK** `sales_deal_quote_valid_until_check` — `CHECK (((quote_valid_until IS NULL) OR ((quote_issued_on IS NOT NULL) AND (quote_valid_until >= quote_issued_on))))`
- **CHECK** `sales_deal_source_code_check` — `CHECK (((source_code IS NULL) OR (btrim(source_code) <> ''::text)))`
- **CHECK** `sales_deal_stage_position_check` — `CHECK ((stage_position >= 0))`
- **CHECK** `sales_deal_title_check` — `CHECK ((btrim(title) <> ''::text))`
- **CHECK** `sales_deal_warranty_terms_check` — `CHECK (((warranty_terms IS NULL) OR (btrim(warranty_terms) <> ''::text)))`
- **FOREIGN KEY** `sales_deal_sales_pipeline_stage_membership_fkey` — `FOREIGN KEY (sales_pipeline_id, sales_pipeline_stage_id) REFERENCES sales_pipeline_stage(sales_pipeline_id, id)`

## Indexes

- `sales_deal_contract_ends_on_idx` — `btree (contract_ends_on) WHERE ((contract_ends_on IS NOT NULL) AND (deleted_at IS NULL))`
- `sales_deal_team_owner_opened_on_idx` — `btree (team_id, owner_member_id, opened_on) WHERE (deleted_at IS NULL)`
- `sales_deal_team_pipeline_stage_position_idx` — `btree (team_id, sales_pipeline_id, sales_pipeline_stage_id, stage_position) WHERE (deleted_at IS NULL)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [contract_status](contract_status.md) | N:1 | `sales_deal.contract_status_id` → `contract_status.id` |
| [customer_company](customer_company.md) | N:1 | `sales_deal.customer_company_id` → `customer_company.id` |
| [customer_contact](customer_contact.md) | N:1 | `sales_deal.customer_contact_id` → `customer_contact.id` |
| [member](member.md) | N:1 | `sales_deal.owner_member_id` → `member.id` |
| [product](product.md) | N:1 | `sales_deal.product_id` → `product.id` |
| [quote_status](quote_status.md) | N:1 | `sales_deal.quote_status_id` → `quote_status.id` |
| [sales_deal_type](sales_deal_type.md) | N:1 | `sales_deal.sales_deal_type_id` → `sales_deal_type.id` |
| [sales_pipeline_stage](sales_pipeline_stage.md) | N:1 | `sales_deal.sales_pipeline_id, sales_deal.sales_pipeline_stage_id` → `sales_pipeline_stage.sales_pipeline_id, sales_pipeline_stage.id` |
| [team](team.md) | N:1 | `sales_deal.team_id` → `team.id` |
| [activity](activity.md) | 1:N | `activity.sales_deal_id` → `sales_deal.id` |
| [contract_next_meeting_suggestion](contract_next_meeting_suggestion.md) | 1:1 | `contract_next_meeting_suggestion.sales_deal_id` → `sales_deal.id` |
| [document](document.md) | 1:N | `document.sales_deal_id` → `sales_deal.id` |
| [purchase_order](purchase_order.md) | 1:N | `purchase_order.sales_deal_id` → `sales_deal.id` |
| [report](report.md) | 1:N | `report.sales_deal_id` → `sales_deal.id` |
| [sales_deal_item](sales_deal_item.md) | 1:N | `sales_deal_item.sales_deal_id` → `sales_deal.id` |
| [sales_deal_participant](sales_deal_participant.md) | 1:N | `sales_deal_participant.sales_deal_id` → `sales_deal.id` |
| [support_request](support_request.md) | 1:N | `support_request.sales_deal_id, support_request.customer_company_id` → `sales_deal.id, sales_deal.customer_company_id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
