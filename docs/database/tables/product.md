# product

팀이 판매하는 제품의 기본 정보와 단가를 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `name` | TEXT | – | NO | – | 제품 이름 |
| `active` | BOOLEAN | – | NO | `true` | 판매 여부 |
| `category_code` | TEXT | – | NO | – | 제품 분류 (system / probe / consumable) |
| `unit_price` | BIGINT | – | NO | – | 판매 단가 (원) |
| `shelf_life_months` | INTEGER | – | YES | – | 유효 기간 (개월) |
| `memo` | TEXT | – | YES | – | 메모 |
| `image_storage_key` | TEXT | – | YES | – | 제품 이미지 스토리지 키 |

## Constraints

- **CHECK** `product_category_code_check` — `CHECK ((category_code = ANY (ARRAY['system'::text, 'probe'::text, 'consumable'::text])))`
- **CHECK** `product_name_check` — `CHECK ((btrim(name) <> ''::text))`
- **CHECK** `product_shelf_life_months_check` — `CHECK (((shelf_life_months IS NULL) OR (shelf_life_months > 0)))`
- **CHECK** `product_unit_price_check` — `CHECK ((unit_price >= 0))`

## Indexes

- `product_team_active_idx` — `btree (team_id, active)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [team](team.md) | N:1 | `product.team_id` → `team.id` |
| [activity](activity.md) | 1:N | `activity.product_id` → `product.id` |
| [document](document.md) | 1:N | `document.product_id` → `product.id` |
| [purchase_order_item](purchase_order_item.md) | 1:N | `purchase_order_item.product_id` → `product.id` |
| [sales_deal](sales_deal.md) | 1:N | `sales_deal.product_id` → `product.id` |
| [sales_deal_item](sales_deal_item.md) | 1:N | `sales_deal_item.product_id` → `product.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
