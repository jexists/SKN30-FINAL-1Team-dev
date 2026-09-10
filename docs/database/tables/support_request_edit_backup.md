# support_request_edit_backup

고객불만을 고치기 직전 값의 백업

쓰기 전용이다. 읽는 API 도 화면도 없고, 되돌릴 일이 생기면 여기서 직접 꺼낸다.
바뀐 칸만 담지 않고 네 칸을 통째로 적으므로, 한 행만 보면 그때의 본문이 그대로 선다.

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `support_request_id` | UUID | FK → support_request.id | NO | – | 고친 불만 ID |
| `editor_member_id` | UUID | FK → member.id | NO | – | 고친 구성원 ID |
| `edited_at` | TIMESTAMPTZ | – | NO | `now()` | 고친 시각 |
| `title` | TEXT | – | NO | – | 고치기 직전의 제목 |
| `body` | TEXT | – | NO | – | 고치기 직전의 내용 |
| `is_urgent` | BOOLEAN | – | NO | – | 고치기 직전의 긴급 여부 |
| `occurred_at` | TIMESTAMPTZ | – | NO | – | 고치기 직전의 발생 시각 |

## Indexes

- `support_request_edit_backup_request_idx` — `btree (support_request_id, edited_at)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [member](member.md) | N:1 | `support_request_edit_backup.editor_member_id` → `member.id` |
| [support_request](support_request.md) | N:1 | `support_request_edit_backup.support_request_id` → `support_request.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
