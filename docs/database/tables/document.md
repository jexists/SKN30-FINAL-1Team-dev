# document

팀이 보관하는 자료의 분류와 연결 대상을 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `created_by_member_id` | UUID | FK → member.id | NO | – | 등록한 구성원 ID |
| `document_no` | TEXT | – | NO | – | 자료 번호 |
| `category_code` | TEXT | – | NO | – | 자료 분류 코드 |
| `title` | TEXT | – | NO | – | 자료 제목 |
| `description` | TEXT | – | YES | – | 자료 설명 |
| `customer_company_id` | UUID | FK → customer_company.id | YES | – | 연결된 고객사 ID |
| `sales_deal_id` | UUID | FK → sales_deal.id | YES | – | 연결된 거래 ID |
| `purchase_order_id` | UUID | FK → purchase_order.id | YES | – | 연결된 발주 ID |
| `tags` | JSONB | – | NO | `'[]'` | 자료 태그 목록 |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 생성 시각 |
| `customer_contact_id` | UUID | FK → customer_contact.id | YES | – | 연결된 고객 담당자 ID (ORM 미매핑, CHANGELOG 참고) |
| `product_id` | UUID | FK → product.id | YES | – | 연결된 제품 ID |

## Constraints

- **CHECK** `document_category_code_check` — `CHECK ((btrim(category_code) <> ''::text))`
- **CHECK** `document_description_check` — `CHECK (((description IS NULL) OR (btrim(description) <> ''::text)))`
- **CHECK** `document_document_no_check` — `CHECK ((btrim(document_no) <> ''::text))`
- **CHECK** `document_product_or_deal_check` — `CHECK ((NOT ((product_id IS NOT NULL) AND (sales_deal_id IS NOT NULL))))`
- **CHECK** `document_tags_check` — `CHECK ((jsonb_typeof(tags) = 'array'::text))`
- **CHECK** `document_title_check` — `CHECK ((btrim(title) <> ''::text))`

## Indexes

- `document_customer_company_idx` — `btree (customer_company_id) WHERE (customer_company_id IS NOT NULL)`
- `document_customer_contact_idx` — `btree (customer_contact_id) WHERE (customer_contact_id IS NOT NULL)`
- `document_product_idx` — `btree (product_id) WHERE (product_id IS NOT NULL)`
- `document_team_created_idx` — `btree (team_id, created_at DESC)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [member](member.md) | N:1 | `document.created_by_member_id` → `member.id` |
| [customer_company](customer_company.md) | N:1 | `document.customer_company_id` → `customer_company.id` |
| [customer_contact](customer_contact.md) | N:1 | `document.customer_contact_id` → `customer_contact.id` |
| [product](product.md) | N:1 | `document.product_id` → `product.id` |
| [purchase_order](purchase_order.md) | N:1 | `document.purchase_order_id` → `purchase_order.id` |
| [sales_deal](sales_deal.md) | N:1 | `document.sales_deal_id` → `sales_deal.id` |
| [team](team.md) | N:1 | `document.team_id` → `team.id` |
| [document_chunk](document_chunk.md) | 1:N | `document_chunk.document_id` → `document.id` |
| [document_file_audit](document_file_audit.md) | 1:N | `document_file_audit.document_id` → `document.id` |
| [file](file.md) | 1:N | `file.document_id` → `document.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
