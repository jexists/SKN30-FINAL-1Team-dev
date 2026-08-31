# notice_image

공지 본문에 삽입한 이미지 파일을 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `uploaded_by_member_id` | UUID | FK → member.id | NO | – | 업로드한 구성원 ID |
| `storage_key` | TEXT | – | NO | – | 스토리지 파일 키 |
| `media_type` | TEXT | – | NO | – | 파일 MIME 타입 |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 생성 시각 |

## Constraints

- **CHECK** `notice_image_media_type_check` — `CHECK ((btrim(media_type) <> ''::text))`
- **CHECK** `notice_image_storage_key_check1` — `CHECK ((btrim(storage_key) <> ''::text))`

## Indexes

- `notice_image_team_idx` — `btree (team_id)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [team](team.md) | N:1 | `notice_image.team_id` → `team.id` |
| [member](member.md) | N:1 | `notice_image.uploaded_by_member_id` → `member.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
