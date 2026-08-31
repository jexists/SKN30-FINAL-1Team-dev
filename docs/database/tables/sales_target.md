# sales_target

구성원별·고객사별 월 매출 목표 금액을 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `owner_member_id` | UUID | FK → member.id | NO | – | 목표를 가진 구성원 ID |
| `customer_company_id` | UUID | FK → customer_company.id | NO | – | 목표 대상 고객사 ID |
| `target_month` | DATE | – | NO | – | 목표 월 (해당 월 1일) |
| `target_amount` | BIGINT | – | NO | – | 목표 금액 (원) |

## Constraints

- **UNIQUE** `sales_target_owner_member_id_customer_company_id_target_mon_key` — `UNIQUE (owner_member_id, customer_company_id, target_month)`
- **CHECK** `sales_target_target_amount_check` — `CHECK ((target_amount >= 0))`
- **CHECK** `sales_target_target_month_check` — `CHECK ((EXTRACT(day FROM target_month) = (1)::numeric))`

## Indexes

- `sales_target_month_owner_idx` — `btree (target_month, owner_member_id)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [customer_company](customer_company.md) | N:1 | `sales_target.customer_company_id` → `customer_company.id` |
| [member](member.md) | N:1 | `sales_target.owner_member_id` → `member.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
