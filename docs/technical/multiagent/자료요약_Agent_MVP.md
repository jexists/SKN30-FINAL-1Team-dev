# 자료요약 Agent MVP

자료실 파일을 업로드한 뒤 원문 추출, 문서 요약, RAG 청크 저장까지 처리하는 백엔드 기능이다.
영업·계약관리 Agent는 같은 팀 범위의 `GET /api/documents/rag-search`를 통해 출처가 붙은 청크를 조회한다.

## 처리 흐름

```text
자료실 업로드
  → POST /api/documents/{document_id}/files/{file_id}/process
  → TXT·MD·JSON 추출
  → 구조화 요약
  → document_chunk 저장
  → GET /api/documents/rag-search?q=...
```

업로드와 처리는 분리되어 있다. 업로드 직후 자동으로 외부 LLM을 호출하지 않으며, 화면의 `AI 요약` 버튼이 처리 API를 호출한다.

## Runpod·AWS 없이 먼저 검증하는 범위

다음 입력은 OCR 서버나 AWS 작업 큐 없이 검증할 수 있다.

- TXT·MD·HTML·HWP·DOCX·PPTX
- 텍스트 레이어가 있는 PDF
- OpenAI 호환 LLM을 이용한 구조화 요약
- 로컬 임베딩 또는 키워드 기반 RAG fallback
- `txt`·`md`·`json`·요약 Markdown 산출물 다운로드
- `briefing-context`의 `summaries`·`sources` 응답

스캔 PDF와 이미지에서 텍스트를 읽는 단계는 OCR 제공자가 필요하다. `OCR_PROVIDER=none`인
상태에서는 원문을 추측해 저장하지 않고 처리 결과를 실패로 남긴다. 명함 이미지는 OCR 서버가
없으면 고객 등록 화면에서 직접 입력할 수 있으며, 자동 고객 저장은 하지 않는다.

AWS 영속 큐가 없는 환경에서는 현재 처리 요청이 FastAPI `BackgroundTasks`로 실행된다. 운영
배포에서 프로세스 재시작 중 작업 유실을 막으려면 이후 SQS 등 영속 큐를 별도로 적용해야 한다.

명함 중복 후보 확인은 OCR과 분리되어 있다. OCR 결과를 사용자 등록 폼에 넣은 뒤 다음 API를
호출하면 같은 팀의 기존 담당자를 전화번호·이메일·이름/회사 조합으로 조회한다.

```http
POST /api/business-cards/matches
Content-Type: application/json
```

이 API는 후보와 `matched_by`만 반환하며 고객을 자동 저장하거나 병합하지 않는다. 최종 등록은
사용자가 등록 폼에서 값을 확인한 뒤 기존 `POST /api/customer-contacts`를 호출한다.

등록 시 명함 원본을 보관하는 흐름에서는 고객 등록 성공 후 다음 API가 호출된다.

```http
POST /api/business-cards/archive
Content-Type: multipart/form-data

contact_id={customer_contact_id}
image={original_business_card_image}
```

이 API는 명함 이미지를 Storage에 저장하고 `document.category_code=business_card`인 자료실
문서와 연결한다. 문서의 `customer_contact_id`로 등록 담당자를 추적할 수 있으며, 원본 저장이
실패해도 이미 완료된 고객 등록을 자동으로 되돌리지는 않는다. 실패 시 화면에서 재업로드를
안내한다.

## 지원 형식

| 형식 | 처리 방식 |
|---|---|
| TXT·MD | UTF-8 텍스트 추출 |
| HTML | 태그 제거 후 텍스트 추출 |
| DOCX | 문단·표를 OOXML에서 추출 |
| PPTX | 슬라이드별 텍스트 추출 |
| 텍스트 PDF | `pypdf`로 페이지별 추출 |
| 스캔 PDF·이미지 | `OCR_PROVIDER=runpod`, `azure` 또는 `local` 설정 시 OCR 어댑터 |
| HWP | `hwp5txt`/`hwp5txt.exe` 우선, 없으면 LibreOffice `soffice` fallback (`HWP5TXT_PATH`·`SOFFICE_PATH`) |

스캔 PDF에서 텍스트가 비어 있으면 `ocr_required`로 실패시키며, 깨진 텍스트를 RAG에 등록하지 않는다.

PDF는 `pdf-inspector`의 페이지별 Markdown API를 우선 사용한다. 페이지별 추출 결과에서
OCR 필요 페이지가 하나라도 있으면 해당 문서는 OCR Provider로 넘긴 뒤, 페이지 번호와
OCR 출처를 보존한다. RAG 청크에는 `page_start`·`page_end`를 저장해 브리핑 근거에
원본 페이지를 표시할 수 있다.

## API

### 처리 시작

```http
POST /api/documents/{document_id}/files/{file_id}/process
```

### 처리 결과

```http
GET /api/documents/{document_id}/files/{file_id}/summary
```

### 결과 파일

```http
GET /api/documents/{document_id}/files/{file_id}/artifacts/txt
GET /api/documents/{document_id}/files/{file_id}/artifacts/text
GET /api/documents/{document_id}/files/{file_id}/artifacts/md
GET /api/documents/{document_id}/files/{file_id}/artifacts/json
GET /api/documents/{document_id}/files/{file_id}/artifacts/summary
```

### RAG 조회

```http
GET /api/documents/rag-search?q=계약기간&limit=5
GET /api/documents/rag-search?q=납기&document_id={document_id}
```

영업·계약관리 Agent가 브리핑에 바로 사용할 수 있도록 검색 근거와 해당 파일의
저장 요약을 한 번에 반환하는 문맥 API도 제공한다.

```http
GET /api/documents/briefing-context?q=계약기간&limit=5
GET /api/documents/briefing-context?q=납기&document_id={document_id}
GET /api/documents/briefing-context?q=납기&sales_deal_id={sales_deal_id}
```

응답은 `summaries`와 `sources`로 나뉜다. `summaries`는 자료요약 Agent의
`summary_markdown`·`summary_payload`를, `sources`는 근거 청크·출처 파일명·검색 점수를
담는다. `sales_deal_id`를 지정하면 해당 딜에 연결된 자료만 검색한다. 영업·계약관리
Agent는 이 응답을 브리핑 프롬프트의 `document_context`로 전달할 수 있다.

백엔드에서 이미 조회한 문맥을 LLM 입력에 넣을 때는 다음 어댑터를 사용한다.

```python
from app.services.sales_context import to_briefing_prompt_block

document_context = to_briefing_prompt_block(context)
```

어댑터는 요약과 검색 근거를 문서명·페이지와 함께 묶고, 문서 데이터의 `<`, `>`, `&`를
이스케이프하며, 기본 입력 길이를 제한한다. 구조화된 `context` 응답은 감사·화면 표시용으로
별도 보존하고, 변환된 문자열은 LLM 프롬프트에만 사용한다.

`sources`에는 `page_start`·`page_end`가 포함되며, 값이 없으면 해당 추출기가 페이지
경계를 제공하지 않은 문서다.

임베딩 설정이 있으면 저장된 임베딩의 코사인 유사도로 조회하고, 없으면 키워드 점수로 fallback한다. 대규모 운영에서는 `embedding jsonb`를 pgvector 컬럼으로 전환해야 한다.

## 환경변수

```env
LLM_API_URL=https://api.openai.com/v1/responses
LLM_API_KEY=
OPENAI_API_KEY=
LLM_MODEL=

EMBEDDING_API_URL=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=
```

`EMBEDDING_API_URL`은 OpenAI 호환 임베딩 API의 `/embeddings` 엔드포인트를 사용한다. 미설정 상태에서도 문서 처리와 출처 보존 키워드 검색은 동작한다.

스캔 PDF·이미지 OCR은 다음 값을 설정한다.

```env
OCR_PROVIDER=azure
OCR_API_URL=https://{resource}.cognitiveservices.azure.com/documentintelligence/documentModels/prebuilt-layout:analyze?api-version=2024-11-30
OCR_API_KEY=
```

OCR 결과는 텍스트·표·페이지 정보를 공통 JSON으로 정규화한 뒤 기존 TXT·MD·RAG 흐름으로 들어간다.

Runpod을 사용할 때는 `OCR_API_URL`에 Serverless endpoint URL을 넣고, 백엔드는 작은 파일만
inline Base64로 전달한다. 큰 원본은 Supabase Storage의 짧은 서명 URL을 Runpod 워커에 전달한다.
워커 계약은 [Runpod OCR 워커 계약](./Runpod_OCR_워커_계약.md)을 따른다.

```env
OCR_PROVIDER=runpod
OCR_API_URL=https://api.runpod.ai/v2/{ENDPOINT_ID}
OCR_API_KEY=
OCR_RUNPOD_WAIT_SECONDS=120
OCR_RUNPOD_INLINE_MAX_BYTES=14680064
OCR_RUNPOD_SIGNED_URL_EXPIRES_SECONDS=300
```

## Mac·Windows 호환성

PDF·DOCX·PPTX·HTML 추출은 Python 표준 라이브러리와 `pypdf`를 사용한다. Runpod·Azure OCR은 HTTP API로 호출하므로 운영체제별 OCR 실행 파일 차이에 의존하지 않는다.

HWP만 외부 실행 파일을 사용한다. Windows에서는 임시 HWP 파일을 닫은 뒤 `hwp5txt.exe`를 실행하고, 해당 실행 파일이 없으면 LibreOffice `soffice` headless 변환을 사용한다. 두 경우 모두 임시 파일과 프로필을 처리 후 삭제해 파일 잠금 문제를 피한다. CI는 Ubuntu·macOS·Windows에서 백엔드 테스트를 실행한다.

로컬 OCR 엔진을 운영체제별로 직접 설치하는 대신 Runpod OCR을 API로 사용하는 경로를 운영 기본값으로 둔다. Mac·Windows의 GPU·런타임 차이는 Runpod 워커에서 격리한다. 로컬 PaddleOCR는 개발·장애 대응용 별도 워커로 유지한다.

## DB 적용

기존 baseline을 적용한 뒤 다음 SQL을 Supabase SQL Editor에서 실행한다.

```text
backend/sql/20260825_0005_document_summary.sql
backend/sql/20260825_0006_business_card_archive.sql
backend/sql/20260825_0007_runtime_schema_alignment.sql
```

이 migration은 `file`에 추출·요약 결과를 추가하고, RAG 청크용 `document_chunk` 테이블을 생성한다.
두 번째 migration은 명함 원본 자료실 문서와 `customer_contact`를 연결하는 컬럼·인덱스를 추가한다.
세 번째 migration은 기존 `notice` 스키마와 고객 연락처 source 값을 현재 API 계약에 맞춘다.
