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

```bash
python -m scripts.windows_ocr_smoke
python -m scripts.windows_ocr_smoke --file /absolute/path/to/business-card.jpeg
# 같은 방식으로 직접 실행해도 된다.
python scripts/windows_ocr_smoke.py --file /absolute/path/to/business-card.jpeg
```

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
