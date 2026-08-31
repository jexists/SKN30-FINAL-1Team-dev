# support_response

접수된 불만에 대한 담당자 응대 이력을 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `support_request_id` | UUID | FK → support_request.id | NO | – | 불만 접수 ID |
| `responder_member_id` | UUID | FK → member.id | NO | – | 응대한 구성원 ID |
| `body` | TEXT | – | NO | – | 응대 내용 |
| `responded_at` | TIMESTAMPTZ | – | NO | `now()` | 응대 시각 |

## Constraints

- **CHECK** `support_response_body_check` — `CHECK ((btrim(body) <> ''::text))`

## Indexes

- `support_response_support_request_responded_idx` — `btree (support_request_id, responded_at)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [member](member.md) | N:1 | `support_response.responder_member_id` → `member.id` |
| [support_request](support_request.md) | N:1 | `support_response.support_request_id` → `support_request.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
