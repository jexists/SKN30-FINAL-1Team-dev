# support_request

고객사가 제기한 불만·요청 접수 내용을 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `assignee_member_id` | UUID | FK → member.id | NO | – | 처리 담당 구성원 ID |
| `title` | TEXT | – | NO | – | 불만 제목 |
| `body` | TEXT | – | NO | – | 불만 내용 |
| `is_urgent` | BOOLEAN | – | NO | `false` | 긴급 여부 |
| `status_code` | TEXT | – | NO | – | 처리 상태 (received / diagnosing / in_progress / completed) |
| `registered_at` | TIMESTAMPTZ | – | NO | `now()` | 접수 시각 |
| `customer_company_id` | UUID | FK → sales_deal (복합 FK) | NO | – | 불만을 제기한 고객사 ID |
| `sales_deal_id` | UUID | FK → sales_deal (복합 FK) | NO | – | 관련 거래 ID |
| `occurred_at` | TIMESTAMPTZ | – | NO | – | 불만 발생 시각 |

## Constraints

- **CHECK** `support_request_body_check` — `CHECK ((btrim(body) <> ''::text))`
- **CHECK** `support_request_status_code_check` — `CHECK ((status_code = ANY (ARRAY['received'::text, 'diagnosing'::text, 'in_progress'::text, 'completed'::text])))`
- **CHECK** `support_request_title_check` — `CHECK ((btrim(title) <> ''::text))`
- **FOREIGN KEY** `support_request_sales_deal_company_membership_fkey` — `FOREIGN KEY (sales_deal_id, customer_company_id) REFERENCES sales_deal(id, customer_company_id) ON UPDATE CASCADE`

## Indexes

- `support_request_sales_deal_company_idx` — `btree (sales_deal_id, customer_company_id)`
- `support_request_team_assignee_status_idx` — `btree (team_id, assignee_member_id, status_code)`
- `support_request_team_company_idx` — `btree (team_id, customer_company_id)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [member](member.md) | N:1 | `support_request.assignee_member_id` → `member.id` |
| [sales_deal](sales_deal.md) | N:1 | `support_request.sales_deal_id, support_request.customer_company_id` → `sales_deal.id, sales_deal.customer_company_id` |
| [team](team.md) | N:1 | `support_request.team_id` → `team.id` |
| [support_response](support_response.md) | 1:N | `support_response.support_request_id` → `support_request.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
