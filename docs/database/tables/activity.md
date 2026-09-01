# activity

고객 미팅 일정과 진행 결과를 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `owner_member_id` | UUID | FK → member.id | NO | – | 담당 구성원 ID |
| `customer_contact_id` | UUID | FK → customer_contact.id | YES | – | 고객 담당자 ID |
| `end_user_contact_id` | UUID | FK → customer_contact.id | YES | – | 실사용자 담당자 ID |
| `title` | TEXT | – | NO | – | 일정 제목 |
| `starts_at` | TIMESTAMPTZ | – | NO | – | 시작 시각 |
| `ends_at` | TIMESTAMPTZ | – | YES | – | 종료 시각 |
| `all_day` | BOOLEAN | – | NO | `false` | 종일 일정 여부 |
| `due_at` | TIMESTAMPTZ | – | YES | – | 기한 시각 |
| `location` | TEXT | – | YES | – | 장소 |
| `completed_at` | TIMESTAMPTZ | – | YES | – | 완료 처리 시각 |
| `note` | TEXT | – | YES | – | 미팅 메모 |
| `deleted_at` | TIMESTAMPTZ | – | YES | – | 삭제 시각 (NULL 이면 사용 중) |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 생성 시각 |
| `updated_at` | TIMESTAMPTZ | – | NO | `now()` | 수정 시각 |
| `product_id` | UUID | FK → product.id | YES | – | 관련 제품 ID |
| `sales_deal_id` | UUID | FK → sales_deal.id | YES | – | 관련 거래 ID |
| `purchase_order_id` | UUID | FK → purchase_order.id | YES | – | 관련 발주 ID |
| `activity_category_id` | UUID | FK → activity_category.id | NO | – | 미팅 분류 ID |
| `activity_action_tag_id` | UUID | FK → activity_action_tag.id | YES | – | 후속 조치 태그 ID |

## Constraints

- **CHECK** `activity_ends_after_start` — `CHECK (((ends_at IS NULL) OR (ends_at > starts_at)))`
- **CHECK** `activity_location_check` — `CHECK (((location IS NULL) OR (btrim(location) <> ''::text)))`
- **CHECK** `activity_note_check` — `CHECK (((note IS NULL) OR (btrim(note) <> ''::text)))`
- **CHECK** `activity_title_check` — `CHECK ((btrim(title) <> ''::text))`

## Indexes

- `activity_customer_contact_idx` — `btree (customer_contact_id) WHERE ((customer_contact_id IS NOT NULL) AND (deleted_at IS NULL))`
- `activity_product_idx` — `btree (product_id) WHERE ((product_id IS NOT NULL) AND (deleted_at IS NULL))`
- `activity_purchase_order_idx` — `btree (purchase_order_id) WHERE ((purchase_order_id IS NOT NULL) AND (deleted_at IS NULL))`
- `activity_sales_deal_idx` — `btree (sales_deal_id) WHERE ((sales_deal_id IS NOT NULL) AND (deleted_at IS NULL))`
- `activity_team_owner_starts_idx` — `btree (team_id, owner_member_id, starts_at) WHERE (deleted_at IS NULL)`
- `activity_team_starts_idx` — `btree (team_id, starts_at) WHERE (deleted_at IS NULL)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [activity_action_tag](activity_action_tag.md) | N:1 | `activity.activity_action_tag_id` → `activity_action_tag.id` |
| [activity_category](activity_category.md) | N:1 | `activity.activity_category_id` → `activity_category.id` |
| [customer_contact](customer_contact.md) | N:1 | `activity.customer_contact_id` → `customer_contact.id` |
| [customer_contact](customer_contact.md) | N:1 | `activity.end_user_contact_id` → `customer_contact.id` |
| [member](member.md) | N:1 | `activity.owner_member_id` → `member.id` |
| [product](product.md) | N:1 | `activity.product_id` → `product.id` |
| [purchase_order](purchase_order.md) | N:1 | `activity.purchase_order_id` → `purchase_order.id` |
| [sales_deal](sales_deal.md) | N:1 | `activity.sales_deal_id` → `sales_deal.id` |
| [team](team.md) | N:1 | `activity.team_id` → `team.id` |
| [activity_companion](activity_companion.md) | 1:N | `activity_companion.activity_id` → `activity.id` |
| [report](report.md) | 1:N | `report.source_activity_id` → `activity.id` |
| [report_activity](report_activity.md) | 1:N | `report_activity.activity_id` → `activity.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
