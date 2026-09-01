# purchase_order_item

발주서에 포함된 제품 품목과 수량을 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `purchase_order_id` | UUID | FK → purchase_order.id | NO | – | 발주 ID |
| `product_id` | UUID | FK → product.id | NO | – | 제품 ID |
| `quantity` | INTEGER | – | NO | – | 수량 |
| `unit_price` | BIGINT | – | NO | – | 단가 (원) |
| `position` | INTEGER | – | NO | – | 발주서 품목 순서 |

## Constraints

- **CHECK** `purchase_order_item_position_check` — `CHECK (("position" >= 0))`
- **CHECK** `purchase_order_item_quantity_check` — `CHECK ((quantity > 0))`
- **CHECK** `purchase_order_item_unit_price_check` — `CHECK ((unit_price >= 0))`

## Indexes

- `purchase_order_item_purchase_order_position_idx` — `btree (purchase_order_id, "position")`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [product](product.md) | N:1 | `purchase_order_item.product_id` → `product.id` |
| [purchase_order](purchase_order.md) | N:1 | `purchase_order_item.purchase_order_id` → `purchase_order.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
