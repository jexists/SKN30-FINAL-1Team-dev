# notice_target

지시사항(DIRECTIVE)을 받을 구성원을 연결

> `notice` 와 `member` 를 잇는 N:M 연결 테이블. 두 컬럼이 복합 기본 키다.

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `notice_id` | UUID | PK, FK → notice.id | NO | – | 공지 ID |
| `member_id` | UUID | PK, FK → member.id | NO | – | 구성원 ID |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 지정 시각 (표시 순서 기준) |

## Indexes

- `notice_target_member_idx` — `btree (member_id)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [member](member.md) | N:1 | `notice_target.member_id` → `member.id` |
| [notice](notice.md) | N:1 | `notice_target.notice_id` → `notice.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
