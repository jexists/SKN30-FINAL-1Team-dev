# sales_deal_participant

거래 미팅에 참석하는 고객 담당자를 연결

> `sales_deal` 와 `customer_contact` 를 잇는 N:M 연결 테이블. 두 컬럼이 복합 기본 키다.

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `sales_deal_id` | UUID | PK, FK → sales_deal.id | NO | – | 거래 ID |
| `customer_contact_id` | UUID | PK, FK → customer_contact.id | NO | – | 참석 고객 담당자 ID |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 지정 시각 |

## Indexes

- `sales_deal_participant_contact_idx` — `btree (customer_contact_id)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [customer_contact](customer_contact.md) | N:1 | `sales_deal_participant.customer_contact_id` → `customer_contact.id` |
| [sales_deal](sales_deal.md) | N:1 | `sales_deal_participant.sales_deal_id` → `sales_deal.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
