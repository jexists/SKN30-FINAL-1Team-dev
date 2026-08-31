# sales_deal_item

거래 견적에 포함된 제품 품목과 수량을 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `sales_deal_id` | UUID | FK → sales_deal.id | NO | – | 거래 ID |
| `product_id` | UUID | FK → product.id | NO | – | 제품 ID |
| `quantity` | INTEGER | – | NO | – | 수량 |
| `unit_price` | BIGINT | – | NO | – | 단가 (원) |
| `position` | INTEGER | – | NO | – | 견적서 품목 순서 |

## Constraints

- **CHECK** `sales_deal_item_position_check` — `CHECK (("position" >= 0))`
- **CHECK** `sales_deal_item_quantity_check` — `CHECK ((quantity > 0))`
- **CHECK** `sales_deal_item_unit_price_check` — `CHECK ((unit_price >= 0))`

## Indexes

- `sales_deal_item_sales_deal_position_idx` — `btree (sales_deal_id, "position")`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [product](product.md) | N:1 | `sales_deal_item.product_id` → `product.id` |
| [sales_deal](sales_deal.md) | N:1 | `sales_deal_item.sales_deal_id` → `sales_deal.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
