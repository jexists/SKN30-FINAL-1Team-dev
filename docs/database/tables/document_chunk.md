# document_chunk

자료 파일에서 추출한 검색용 텍스트 조각을 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `team_id` | UUID | FK → team.id | NO | – | 소속 팀 ID |
| `document_id` | UUID | FK → document.id | NO | – | 원본 자료 ID |
| `file_id` | UUID | FK → file.id | NO | – | 원본 파일 ID |
| `chunk_no` | INTEGER | – | NO | – | 파일 안에서의 조각 순번 |
| `page_start` | INTEGER | – | YES | – | 조각 시작 페이지 |
| `page_end` | INTEGER | – | YES | – | 조각 종료 페이지 |
| `section` | TEXT | – | YES | – | 조각이 속한 절 제목 |
| `content` | TEXT | – | NO | – | 조각 본문 |
| `metadata` | JSONB | – | NO | `'{}'` | 조각 부가 정보 |
| `embedding` | JSONB | – | YES | – | 조각 임베딩 벡터 |
| `created_at` | TIMESTAMPTZ | – | NO | `now()` | 생성 시각 |

## Constraints

- **UNIQUE** `document_chunk_file_id_chunk_no_key` — `UNIQUE (file_id, chunk_no)`
- **CHECK** `document_chunk_chunk_no_check` — `CHECK ((chunk_no >= 0))`
- **CHECK** `document_chunk_content_check` — `CHECK ((btrim(content) <> ''::text))`
- **CHECK** `document_chunk_page_end_check` — `CHECK (((page_end IS NULL) OR (page_end >= 1)))`
- **CHECK** `document_chunk_page_start_check` — `CHECK (((page_start IS NULL) OR (page_start >= 1)))`
- **CHECK** `document_chunk_section_check` — `CHECK (((section IS NULL) OR (btrim(section) <> ''::text)))`

## Indexes

- `document_chunk_document_idx` — `btree (document_id)`
- `document_chunk_file_idx` — `btree (file_id)`
- `document_chunk_team_idx` — `btree (team_id)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [document](document.md) | N:1 | `document_chunk.document_id` → `document.id` |
| [file](file.md) | N:1 | `document_chunk.file_id` → `file.id` |
| [team](team.md) | N:1 | `document_chunk.team_id` → `team.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
