# customer_company

영업 대상 고객 회사의 기본 정보와 주소를 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `name` | TEXT | – | NO | – | 고객사 이름 |
| `region_code` | TEXT | – | YES | – | 지역 코드 |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 생성 시각 |
| `business_no` | TEXT | – | YES | – | 사업자등록번호 (하이픈 없는 10자리) |
| `postcode` | TEXT | – | YES | – | 우편번호 (5자리) |
| `address` | TEXT | – | YES | – | 기본 주소 |
| `address_detail` | TEXT | – | YES | – | 상세 주소 |

## Constraints

- **CHECK** `customer_company_business_no_check` — `CHECK (((business_no IS NULL) OR (business_no ~ '^[0-9]{10}$'::text)))`
- **CHECK** `customer_company_name_check` — `CHECK ((btrim(name) <> ''::text))`
- **CHECK** `customer_company_postcode_check` — `CHECK (((postcode IS NULL) OR (postcode ~ '^[0-9]{5}$'::text)))`
- **CHECK** `customer_company_region_code_check` — `CHECK (((region_code IS NULL) OR (btrim(region_code) <> ''::text)))`

## Indexes

- `customer_company_team_name_idx` — `btree (team_id, name)`
- `customer_company_team_name_uq` — `btree (team_id, name)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [team](team.md) | N:1 | `customer_company.team_id` → `team.id` |
| [customer_contact](customer_contact.md) | 1:N | `customer_contact.company_id` → `customer_company.id` |
| [document](document.md) | 1:N | `document.customer_company_id` → `customer_company.id` |
| [purchase_order](purchase_order.md) | 1:N | `purchase_order.expected_customer_company_id` → `customer_company.id` |
| [sales_deal](sales_deal.md) | 1:N | `sales_deal.customer_company_id` → `customer_company.id` |
| [sales_target](sales_target.md) | 1:N | `sales_target.customer_company_id` → `customer_company.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
