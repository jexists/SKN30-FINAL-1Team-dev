# file

보고서와 자료에 첨부된 파일과 추출 결과를 관리

## Columns

| Column | Type | Key | Nullable | Default | Description |
|---|---|---|---|---|---|
| `id` | UUID | PK | NO | – | 기본 키 |
| `report_id` | UUID | FK → report.id | YES | – | 첨부된 보고서 ID |
| `document_id` | UUID | FK → document.id | YES | – | 첨부된 자료 ID |
| `version_no` | INTEGER | – | YES | – | 자료 파일은 항상 1. 버전 관리를 쓰지 않아 고정값이며 예전 자료에는 2 이상이 남아 있다 |
| `file_name` | TEXT | – | NO | – | 원본 파일 이름 |
| `storage_key` | TEXT | UNIQUE | NO | – | 스토리지 파일 키 |
| `media_type` | TEXT | – | YES | – | 파일 MIME 타입 |
| `byte_size` | BIGINT | – | NO | – | 파일 크기 (바이트) |
| `processing_status` | TEXT | – | NO | – | 처리 상태 (uploaded / processing / review_required / completed / failed) |
| `extracted_text` | TEXT | – | YES | – | 추출한 평문 텍스트 |
| `uploaded_by_member_id` | UUID | FK → member.id | NO | – | 업로드한 구성원 ID |
| `note` | TEXT | – | YES | – | 첨부 비고 |
| `uploaded_at` | TIMESTAMPTZ | – | NO | `now()` | 업로드 시각 |
| `extracted_markdown` | TEXT | – | YES | – | 추출한 마크다운 본문 |
| `extracted_payload` | JSONB | – | YES | – | 추출 원본 응답 |
| `summary_markdown` | TEXT | – | YES | – | AI 요약 마크다운 |
| `summary_payload` | JSONB | – | YES | – | AI 요약 원본 응답 |
| `processing_error` | TEXT | – | YES | – | 처리 실패 사유 |
| `processed_at` | TIMESTAMPTZ | – | YES | – | 처리 완료 시각 |
| `review_expires_at` | TIMESTAMPTZ | – | YES | – | 검토 기한 시각 |
| `unapproved_expires_at` | TIMESTAMPTZ | – | YES | – | 미승인 상태 만료 시각 |
| `approved_by_member_id` | UUID | FK → member.id | YES | – | 요약을 승인한 구성원 ID |
| `approved_at` | TIMESTAMPTZ | – | YES | – | 요약 승인 시각 |

## Constraints

- **UNIQUE** `file_document_id_version_no_key` — `UNIQUE (document_id, version_no)` (`version_no`가 1로 고정이라 자료 하나에 파일 하나를 보장한다)
- **CHECK** `file_byte_size_check` — `CHECK ((byte_size >= 0))`
- **CHECK** `file_document_version` — `CHECK ((((document_id IS NOT NULL) AND (version_no IS NOT NULL) AND (version_no >= 1)) OR ((report_id IS NOT NULL) AND (version_no IS NULL))))`
- **CHECK** `file_exactly_one_parent` — `CHECK ((num_nonnulls(report_id, document_id) = 1))`
- **CHECK** `file_extracted_markdown_check` — `CHECK (((extracted_markdown IS NULL) OR (btrim(extracted_markdown) <> ''::text)))`
- **CHECK** `file_extracted_text_check` — `CHECK (((extracted_text IS NULL) OR (btrim(extracted_text) <> ''::text)))`
- **CHECK** `file_file_name_check` — `CHECK ((btrim(file_name) <> ''::text))`
- **CHECK** `file_media_type_check` — `CHECK (((media_type IS NULL) OR (btrim(media_type) <> ''::text)))`
- **CHECK** `file_note_check` — `CHECK (((note IS NULL) OR (btrim(note) <> ''::text)))`
- **CHECK** `file_processing_error_check` — `CHECK (((processing_error IS NULL) OR (btrim(processing_error) <> ''::text)))`
- **CHECK** `file_processing_status_check` — `CHECK ((processing_status = ANY (ARRAY['uploaded'::text, 'processing'::text, 'review_required'::text, 'completed'::text, 'failed'::text])))`
- **CHECK** `file_storage_key_check` — `CHECK ((btrim(storage_key) <> ''::text))`
- **CHECK** `file_summary_markdown_check` — `CHECK (((summary_markdown IS NULL) OR (btrim(summary_markdown) <> ''::text)))`

## Indexes

- `file_report_idx` — `btree (report_id) WHERE (report_id IS NOT NULL)`
- `file_review_expiry_idx` — `btree (review_expires_at) WHERE (processing_status = 'review_required'::text)`
- `file_unapproved_expiry_idx` — `btree (unapproved_expires_at) WHERE (processing_status <> 'completed'::text)`

## Relations

| 상대 테이블 | 관계 | FK |
|---|---|---|
| [member](member.md) | N:1 | `file.approved_by_member_id` → `member.id` |
| [document](document.md) | N:1 | `file.document_id` → `document.id` |
| [report](report.md) | N:1 | `file.report_id` → `report.id` |
| [member](member.md) | N:1 | `file.uploaded_by_member_id` → `member.id` |
| [document_chunk](document_chunk.md) | 1:N | `document_chunk.file_id` → `file.id` |
| [document_file_audit](document_file_audit.md) | 1:N | `document_file_audit.file_id` → `file.id` |

---

[← 전체 테이블 목록](../README.md) · [관계 전체](../RELATIONS.md) · [Interactive ERD](../erd.html)
