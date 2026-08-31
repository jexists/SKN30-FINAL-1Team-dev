# customer_contact_assignee

고객 담당자를 맡은 내부 구성원을 연결

> `customer_contact` 와 `member` 를 잇는 N:M 연결 테이블. 두 컬럼이 복합 기본 키다.

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `customer_contact_id` | UUID | PK, FK → customer_contact.id | NO | – | 고객 담당자 ID |
| `member_id` | UUID | PK, FK → member.id | NO | – | 담당 구성원 ID (주담당도 포함) |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 지정 시각 |

## Indexes

- `customer_contact_assignee_member_idx` — `btree (member_id)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [customer_contact](customer_contact.md) | N:1 | `customer_contact_assignee.customer_contact_id` → `customer_contact.id` |
| [member](member.md) | N:1 | `customer_contact_assignee.member_id` → `member.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
