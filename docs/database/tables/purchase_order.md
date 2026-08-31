# purchase_order

거래에 필요한 제품을 공급처에 넣은 발주를 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `order_no` | TEXT | – | NO | – | 발주 번호 |
| `sales_deal_id` | UUID | FK → sales_deal.id | NO | – | 발주 근거가 되는 거래 ID |
| `supplier_name` | TEXT | – | NO | – | 공급처 이름 |
| `ordered_on` | DATE | – | NO | – | 발주일 |
| `due_on` | DATE | – | NO | – | 납기일 |
| `expected_receipt_on` | DATE | – | NO | – | 입고 예정일 |
| `memo` | TEXT | – | YES | – | 메모 |
| `deleted_at` | TIMESTAMPTZ | – | YES | – | 삭제 시각 (NULL 이면 사용 중) |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 생성 시각 |
| `updated_at` | TIMESTAMPTZ | – | NO | `now()` | 수정 시각 |
| `purchase_order_status_id` | UUID | FK → purchase_order_status.id | NO | – | 발주 상태 ID |
| `request_department` | TEXT | – | NO | `'영업팀'` | 요청 부서 |
| `cooperation_department` | TEXT | – | NO | `'생산팀'` | 협조 부서 |
| `created_by_member_id` | UUID | FK → member.id | NO | – | 작성한 구성원 ID |
| `expected_customer_company_id` | UUID | FK → customer_company.id | NO | – | 납품 예정 거래처 ID |

## Constraints

- **UNIQUE** `purchase_order_team_id_order_no_key` — `UNIQUE (team_id, order_no)`
- **CHECK** `purchase_order_cooperation_department_check` — `CHECK ((btrim(cooperation_department) <> ''::text))`
- **CHECK** `purchase_order_due_on_order_check` — `CHECK ((due_on >= ordered_on))`
- **CHECK** `purchase_order_expected_receipt_on_order_check` — `CHECK ((expected_receipt_on >= ordered_on))`
- **CHECK** `purchase_order_memo_check` — `CHECK (((memo IS NULL) OR (btrim(memo) <> ''::text)))`
- **CHECK** `purchase_order_order_no_check` — `CHECK ((btrim(order_no) <> ''::text))`
- **CHECK** `purchase_order_request_department_check` — `CHECK ((btrim(request_department) <> ''::text))`
- **CHECK** `purchase_order_supplier_name_check` — `CHECK ((btrim(supplier_name) <> ''::text))`

## Indexes

- `purchase_order_expected_company_idx` — `btree (expected_customer_company_id) WHERE (deleted_at IS NULL)`
- `purchase_order_expected_receipt_idx` — `btree (expected_receipt_on) WHERE (deleted_at IS NULL)`
- `purchase_order_sales_deal_idx` — `btree (sales_deal_id) WHERE (deleted_at IS NULL)`
- `purchase_order_team_due_idx` — `btree (team_id, due_on) WHERE (deleted_at IS NULL)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [member](member.md) | N:1 | `purchase_order.created_by_member_id` → `member.id` |
| [customer_company](customer_company.md) | N:1 | `purchase_order.expected_customer_company_id` → `customer_company.id` |
| [purchase_order_status](purchase_order_status.md) | N:1 | `purchase_order.purchase_order_status_id` → `purchase_order_status.id` |
| [sales_deal](sales_deal.md) | N:1 | `purchase_order.sales_deal_id` → `sales_deal.id` |
| [team](team.md) | N:1 | `purchase_order.team_id` → `team.id` |
| [activity](activity.md) | 1:N | `activity.purchase_order_id` → `purchase_order.id` |
| [document](document.md) | 1:N | `document.purchase_order_id` → `purchase_order.id` |
| [purchase_order_item](purchase_order_item.md) | 1:N | `purchase_order_item.purchase_order_id` → `purchase_order.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
