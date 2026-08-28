# 자료요약 Agent 무료형·로컬 실행

## 목적

이 프로젝트는 외부 OCR·LLM·임베딩 API 없이도 문서요약 Agent의 전체 흐름을 실행할 수 있다. 기존 Azure·외부 LLM 경로는 삭제하지 않고 Provider 설정으로 선택한다.

## 처리 구조

```text
텍스트 PDF       -> pdf-inspector 또는 pypdf
스캔 PDF·이미지  -> PaddleOCR
DOCX·PPTX·HTML   -> 기존 내장 파서 또는 Docling
요약             -> Ollama /api/chat
임베딩           -> SentenceTransformers
RAG              -> PostgreSQL + pgvector 또는 키워드 검색 fallback
```

## 설치

```bash
# 기본 백엔드 의존성
cd backend
uv sync

# PDF 추출·임베딩·로컬 OCR을 백엔드에 추가한다.
uv sync --extra local
```

`local` extra에는 `pdf-inspector`, `pypdfium2`, `onnxruntime`, `paddleocr`, `paddlepaddle`이 포함된다. PDF OCR은 `pdf-inspector`와 `pypdfium2`를 사용하며, 애플리케이션이 Mac·Windows·Linux별 PDFium과 ONNX Runtime 라이브러리를 자동 탐색한다. 경로를 직접 지정해야 하는 환경에서는 `PDFIUM_LIB_PATH`와 `ORT_DYLIB_PATH`를 지정한다.

첫 실행 시 PaddleOCR·pdf-inspector 모델 파일을 내려받을 수 있으므로 개발 환경에서 한 번 네트워크를 허용한다. 이후 OCR은 입력 문서를 외부 API로 보내지 않고 로컬 모델로 처리한다. [가정] 운영 환경의 OS·CPU 아키텍처가 개발 환경과 다르면 해당 환경에서 `uv sync --extra local`과 샘플 OCR을 별도로 검증한다.
모델 캐시는 기본적으로 OS 임시 폴더 아래에 저장되며, 지속 경로가 필요하면 `.env`의
`PDF_INSPECTOR_MODEL_DIRECTORY`와 `PADDLEX_CACHE_HOME`을 지정한다.
PaddleX 모델이 이미 캐시에 있으면 오프라인 환경에서 호스트 확인을 건너뛰도록 앱이
`PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`를 기본 설정한다.

```bash
# 선택 의존성과 버전을 잠금 파일 기준으로 설치한다.
uv sync --extra local
```

로컬 OCR 결과는 공통 페이지 구조로 정규화되어 `text`, `txt`, `md`, `json` artifact와 RAG 청크의 페이지 참조로 이어진다. `text`와 `txt`는 같은 평문 결과를 확장자별로 제공한다.

## Ollama 준비

Ollama를 설치하고 로컬 모델을 준비한다.

```bash
ollama serve
ollama pull <팀에서 검증한 한국어 모델>
```

모델 이름은 임의로 고정하지 않는다. 실제 계약서·견적서·명함 샘플에서 JSON 출력과 한국어 요약을 확인한 뒤 `.env`에 기록한다.

## `.env` 설정

```dotenv
OCR_PROVIDER=local
OCR_LOCAL_LANGUAGE=korean

LLM_PROVIDER=ollama
LLM_API_URL=http://localhost:11434/api/chat
LLM_API_KEY=
LLM_MODEL=<검증한 로컬 모델>

EMBEDDING_PROVIDER=local
EMBEDDING_LOCAL_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

## 실행 순서

1. 백엔드가 PostgreSQL·Supabase Storage에 연결되는지 확인한다.
2. `ollama serve`가 실행 중인지 확인한다.
3. PaddleOCR·pdf-inspector·SentenceTransformers import를 확인한다.
4. 자료실에 TXT·DOCX·PPTX·HTML·텍스트 PDF를 업로드한다.
5. 스캔 PDF·이미지를 업로드하고 로컬 OCR 결과를 확인한다.
6. 요약 결과와 TXT·MD·JSON artifact를 확인한다.
7. RAG 검색에서 임베딩 검색 또는 키워드 fallback을 확인한다.
8. 실제 한국어 명함은 OCR 결과를 사용자 검수한 뒤 CRM에 연결한다.

Windows·Mac에서 로컬 이미지 OCR만 빠르게 확인할 때는 백엔드 디렉터리에서 다음 명령을 사용한다.
파일을 생략하면 개인정보 없는 합성 이미지로 런타임만 검사하고, `--file`을 지정하면 실제
사용자 제공 이미지의 OCR 경로까지 검사한다.
저장소의 백엔드 CI도 Windows runner에서 `OCR_PROVIDER=local`을 명시해 동일한 합성 OCR
smoke test를 `business_card` 경량 프로필로 실행한다. 일반 `document` 프로필은 방향분류·
문서보정 모델 캐시가 추가로 필요하므로 실제 문서 검증 시 별도로 실행한다.

```bash
python -m scripts.windows_ocr_smoke
python -m scripts.windows_ocr_smoke --profile business_card \
  --file /absolute/path/to/business-card.jpeg
# 같은 방식으로 직접 실행해도 된다.
python scripts/windows_ocr_smoke.py --profile business_card \
  --file /absolute/path/to/business-card.jpeg
```

`business_card` 프로필은 명함용 경량 OCR 엔진과 이미지 보정 variant를 사용한다.
고해상도 사진은 `BUSINESS_CARD_MAX_SIDE` 기준으로 축소한 뒤 처리하며, 기본값은
`2400`이다. 메모리가 부족한 Windows 환경에서는 실행 전에 `BUSINESS_CARD_MAX_SIDE=1200`
처럼 낮춰 단계적으로 확인할 수 있다.
현재 명함용 PaddleOCR는 `PP-OCRv5_mobile_det`와
`korean_PP-OCRv5_mobile_rec`를 사용한다. 원본 사진을 카드 보정 전에 먼저 축소해
4K 사진의 CPU 처리시간을 줄이며, 기존 대비·이진화 후보 검사는 유지한다.
로컬 OCR도 `OCR_TIMEOUT_SECONDS`를 적용하므로, CPU 추론이 제한 시간을 넘으면 결과를
저장하지 않고 `local_ocr_timeout` 오류로 반환한다.

실제 문서의 로컬 추출·페이지 보존·청크 구조를 외부 API 없이 점검할 때는 다음 명령을
사용한다. 결과에는 파일명과 품질 지표만 출력하며 원문은 출력하지 않는다.

```bash
python scripts/document_quality_smoke.py --ocr-local /absolute/path/to/document-directory
```

실제 문서를 OpenAI로 요약하는 E2E는 외부 전송을 인지한 경우에만 다음처럼 실행한다.
`--send-to-llm`이 없으면 실행되지 않으며, 출력은 요약 본문이 아닌 품질 지표뿐이다.

```bash
python scripts/document_summary_e2e.py --send-to-llm \
  /absolute/path/to/contract.pdf /absolute/path/to/contract.docx
```

실제 명함의 고객 등록·원본 보관 E2E는 테스트용 계정과 테스트용 이미지 경로를 현재
터미널 세션의 환경변수로만 넣은 뒤 실행한다. 이 과정은 회사·고객·문서 데이터를
생성하므로 [가정] 테스트용 팀과 계정이 준비되어 있어야 하며, 운영 계정으로 바로
실행하지 않는다.

```bash
export SALESLUV_E2E_EMAIL='테스트 계정 이메일'
export SALESLUV_E2E_PASSWORD='테스트 계정 비밀번호'
export SALESLUV_E2E_CARD_PATH='/absolute/path/to/business-card.jpeg'
python scripts/business_card_e2e.py
```

HWP는 `hwp5txt`/`hwp5txt.exe`를 우선 사용하고, 없으면 LibreOffice의 `soffice`를
headless로 사용한다. PATH에 없으면 `.env`의 `HWP5TXT_PATH` 또는 `SOFFICE_PATH`에
실행 파일 경로를 지정한다.

## Provider 동작

| 설정 | 동작 |
|---|---|
| `OCR_PROVIDER=none` | 스캔 문서·이미지는 오류로 중단하고 조용히 저장하지 않음 |
| `OCR_PROVIDER=azure` | Azure Document Intelligence 어댑터 사용 |
| `OCR_PROVIDER=local` | PDF는 pdf-inspector 선택 OCR, 이미지는 PaddleOCR 사용 |
| `LLM_PROVIDER=external` | 기존 외부 Responses 호환 API 사용 |
| `LLM_PROVIDER=ollama` | 로컬 Ollama JSON schema 출력 사용 |
| `EMBEDDING_PROVIDER=none` | 키워드 기반 RAG fallback |
| `EMBEDDING_PROVIDER=external` | 기존 OpenAI 호환 임베딩 API 사용 |
| `EMBEDDING_PROVIDER=local` | SentenceTransformers 로컬 모델 사용 |

## 운영상 주의

- 로컬형은 API 사용료가 없지만 서버·저장소·CPU·메모리 비용은 발생할 수 있다.
- 명함은 이름·회사·직책·전화·이메일을 자동 확정하지 않고 사용자 확인 단계를 둔다.
- Mac·Windows에서 같은 모델·패키지 버전과 같은 입력 샘플을 사용해 재현성을 확인한다.
- OCR·요약·임베딩 모델의 버전과 다운로드 경로를 기록한다.
- 실제 운영 전에는 Azure·CLOVA를 fallback으로 둘지, 외부 전송을 허용하지 않을지 팀 정책으로 결정한다.

## 현재 통합 검증 결과

[검증] 사용자 제공 취업규칙 PDF는 로컬 `pdf-inspector` OCR로 35페이지를 처리했고, 페이지 번호
검증과 비어 있지 않은 RAG 청크 생성을 통과했다.

[검증] 사용자 제공 계약서 DOCX는 로컬 문서 추출로 1페이지를 처리했고, 페이지 번호 검증과
비어 있지 않은 RAG 청크 생성을 통과했다.

[검증] 실제 명함 이미지는 로컬 PaddleOCR에서 텍스트와 전화번호 패턴을 인식했다. 이메일은
기호 주변 공백 또는 OCR 기호 변형을 포함한 별도 정규화·재검증이 필요하다.

[검증] 개인정보가 없는 합성 문서로 OpenAI 구조화 요약 호출을 실행했고, `DocumentSummaryOutput`
스키마 검증과 요약·핵심 항목·추출 필드 반환을 통과했다. 이후 사용자가 허용한 실제 취업규칙
PDF도 Runpod OCR과 OpenAI 구조화 요약까지 통과했으며, 원문과 요약 본문은 로그에 출력하지 않았다.

[검증] 개인정보가 없는 합성 문장 3개로 로컬 SentenceTransformers 임베딩과 코사인 유사도
검색을 실행했고, 벡터 생성과 관련 문장 우선 검색을 통과했다.
모델 캐시가 준비된 환경에서는 `HF_HUB_OFFLINE=1`로 외부 모델 저장소 연결 없이도 임베딩을
생성했다.

[검증] Mac 환경에서 `OCR_PROVIDER=local`로 개인정보 없는 합성 명함을
`business_card` 프로필로 실행했고 `windows_ocr_smoke=passed`를 확인했다. 실제 고해상도
명함은 초기 설정에서 `local_ocr_timeout`이 발생했으나, 입력 사전 축소와 Mobile 모델
적용 후 같은 경로가 `windows_ocr_smoke=passed`로 완료됐다. 같은 검사는 Windows CI의
`windows-latest`에서도 실행되도록 구성되어 있다.

[검증] 로컬 샘플 문서 5건(PDF 4건·DOCX 1건)을 추출·OCR·페이지 보존·청크 생성까지
점검했고 모두 통과했다. 스캔 PDF는 `pdf_inspector_local_ocr`로 처리되며, 모델 캐시가
없을 때는 최초 실행에서 모델을 준비하고 이후 캐시를 재사용한다.

[검증] 기본 백엔드 테스트는 외부 연결 없이 `412 passed, 7 skipped`이며,
OpenAI 계약·일정·브리핑 합성 파이프라인은 실통합 테스트 1건을 통과했다. 외부 실통합
테스트는 `RUN_INTEGRATION_TESTS=true`를 명시해야 실행된다.

[검증] 개인정보 없는 합성 명함·PDF를 Runpod OCR endpoint에 전달해 각각 1페이지,
페이지 번호, Markdown 결과를 확인했다. 명함은 11.4초, PDF는 2.69초에 완료됐다.

[검증] Develop 통합 후 Supabase 헬스·모델 호환성 읽기 검사는 `4 passed`였다. DB의
현재 모델 누락은 없었고, `report.sales_deal_id` 등 기존 레거시 컬럼은 검사 허용 목록으로
분리했다. DB 스키마를 삭제하거나 변경하지는 않았다.

[검증] Supabase 읽기 전용 확인에서 문서 2건·파일 2건·처리 완료 파일 2건·RAG 청크 233개·
임베딩 233개를 확인했다. 실제 저장 데이터의 RAG 검색에서 출처 5건과 저장 요약 2건이 반환됐고,
출처 페이지 참조와 브리핑용 prompt context 생성도 통과했다.

[검증] 개인정보 없는 합성 문서를 Supabase 트랜잭션에 임시 저장해 로컬 임베딩 검색, 페이지
참조 보존, 저장 요약의 브리핑 문맥 결합을 확인한 뒤 롤백한 기존 검증도 유지된다.

[미완료] Windows 실제 환경에서 동일한 문서·명함 입력을 실행하고 Mac 결과와 정확도·처리시간을
비교한다. 개인정보가 있는 원본은 로그에 출력하지 않고 필드별 결과만 비교한다.
[미완료] OCR 필드 정답지와 요약·RAG 질의 정답지를 확정하지 않아 정확도 수치 자체는 아직
산출하지 않았다. 평가 기준과 기록 양식은 `자료요약_Agent_정확도_평가_계획.md`에 정리한다.
