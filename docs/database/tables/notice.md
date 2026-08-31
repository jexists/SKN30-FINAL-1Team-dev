# notice

팀 전체 공지와 특정 구성원 지시사항을 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `author_member_id` | UUID | FK → member.id | NO | – | 작성한 구성원 ID |
| `tag` | TEXT | – | YES | – | 분류 태그 |
| `title` | TEXT | – | NO | – | 제목 |
| `body` | TEXT | – | NO | – | 본문 HTML (저장 전 sanitize) |
| `image_storage_key` | TEXT | – | YES | – | 대표 이미지 스토리지 키 |
| `image_alt` | TEXT | – | YES | – | 대표 이미지 대체 텍스트 |
| `published_at` | TIMESTAMPTZ | – | NO | `now()` | 게시 시각 |
| `due_at` | TIMESTAMPTZ | – | YES | – | 처리 기한 시각 |
| `due_text` | TEXT | – | YES | – | 기한 표시 문구 |
| `type` | TEXT | – | NO | – | 공지 구분 (NOTICE 전체 / DIRECTIVE 지정 수신) |
| `display_start_date` | DATE | – | NO | – | 게시 시작일 (Asia/Seoul, 당일 포함) |
| `display_end_date` | DATE | – | YES | – | 게시 종료일 (당일 포함) |
| `is_hidden` | BOOLEAN | – | NO | `false` | 숨김 여부 |
| `sort_order` | INTEGER | – | NO | `0` | 상단 고정 정렬 순서 |
| `updated_at` | TIMESTAMPTZ | – | NO | `now()` | 수정 시각 |
| `deleted_at` | TIMESTAMPTZ | – | YES | – | 삭제 시각 (NULL 이면 사용 중) |
| `recipient_member_id` | UUID | FK → member.id | YES | – | 수신 구성원 ID (ORM 미매핑, CHANGELOG 참고) |

## Constraints

- **CHECK** `notice_body_check` — `CHECK ((btrim(body) <> ''::text))`
- **CHECK** `notice_display_range_check` — `CHECK (((display_end_date IS NULL) OR (display_end_date >= display_start_date)))`
- **CHECK** `notice_due_text_check` — `CHECK (((due_text IS NULL) OR (btrim(due_text) <> ''::text)))`
- **CHECK** `notice_image_alt_check` — `CHECK (((image_alt IS NULL) OR (btrim(image_alt) <> ''::text)))`
- **CHECK** `notice_image_storage_key_check` — `CHECK (((image_storage_key IS NULL) OR (btrim(image_storage_key) <> ''::text)))`
- **CHECK** `notice_tag_check` — `CHECK (((tag IS NULL) OR (btrim(tag) <> ''::text)))`
- **CHECK** `notice_title_check` — `CHECK ((btrim(title) <> ''::text))`
- **CHECK** `notice_type_check` — `CHECK ((type = ANY (ARRAY['NOTICE'::text, 'DIRECTIVE'::text])))`

## Indexes

- `notice_team_recipient_published_idx` — `btree (team_id, recipient_member_id, published_at DESC)`
- `notice_team_type_order_idx` — `btree (team_id, type, sort_order, published_at DESC) WHERE (deleted_at IS NULL)`
- `notice_visible_idx` — `btree (team_id, type, display_start_date, display_end_date) WHERE ((deleted_at IS NULL) AND (is_hidden = false))`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [member](member.md) | N:1 | `notice.author_member_id` → `member.id` |
| [member](member.md) | N:1 | `notice.recipient_member_id` → `member.id` |
| [team](team.md) | N:1 | `notice.team_id` → `team.id` |
| [notice_target](notice_target.md) | 1:N | `notice_target.notice_id` → `notice.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
