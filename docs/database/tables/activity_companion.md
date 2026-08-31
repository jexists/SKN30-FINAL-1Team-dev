# activity_companion

미팅에 동행한 내부 구성원을 연결

> `activity` 와 `member` 를 잇는 N:M 연결 테이블. 두 컬럼이 복합 기본 키다.

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `activity_id` | UUID | PK, FK → activity.id | NO | – | 미팅 일정 ID |
| `member_id` | UUID | PK, FK → member.id | NO | – | 동행 구성원 ID |

## Indexes

- `activity_companion_member_idx` — `btree (member_id)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [activity](activity.md) | N:1 | `activity_companion.activity_id` → `activity.id` |
| [member](member.md) | N:1 | `activity_companion.member_id` → `member.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
