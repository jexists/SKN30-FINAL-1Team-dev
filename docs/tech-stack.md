# 기술 스택

각 기술의 선정 이유를 정리한 문서입니다. 요약 배지는 [README](../README.md#기술-스택)에 있습니다.

## 현재 사용

`frontend/package.json`과 `backend/pyproject.toml`에 실제로 설치되어 동작하는 스택입니다.

### Frontend

| 기술 | 선정 이유 |
|---|---|
| React 19 | 컴포넌트 기반으로 동적인 화면을 구현하기 쉬움 |
| TypeScript | 타입 오류를 사전에 방지 |
| Vite 8 | 빠른 개발 서버와 빌드 환경 제공 |
| SCSS Modules (sass) | 화면 단위로 스타일 범위를 격리 |
| React Router 8 | 역할·조회 범위에 따른 라우팅 처리 |
| axios | API 호출 공통 처리와 인터셉터 |
| Recharts | 매출·KPI 차트 렌더링 |

### Backend

| 기술 | 선정 이유 |
|---|---|
| FastAPI | Python AI 생태계를 활용하기 쉽고, Swagger UI를 자동 제공해 프론트엔드와 API 협업에 유리 |
| Python 3.13 | AI 라이브러리 호환성과 최신 타입 기능 |
| SQLAlchemy (async) | 비동기 DB 접근과 모델 정의 |
| asyncpg | PostgreSQL 비동기 드라이버 |
| uv | 의존성 설치와 가상환경을 빠르게 재현 |

### Database

| 기술 | 선정 이유 |
|---|---|
| Supabase PostgreSQL | 클라우드 기반으로 팀원 간 DB 공유가 쉬움 |
| pgvector | 관계형 데이터와 문서 임베딩을 한 DB에서 함께 관리 |

### DevOps · Quality

| 기술 | 선정 이유 |
|---|---|
| GitHub Actions | 테스트·빌드 자동화 ([ci-frontend.yml](../.github/workflows/ci-frontend.yml), [ci-backend.yml](../.github/workflows/ci-backend.yml)) |
| oxlint · prettier | 프론트엔드 린트와 포맷 |
| ruff | 백엔드 린트와 포맷 |
| pytest | 백엔드 테스트 |

## 도입 예정 (검토 중)

아직 코드에 포함되지 않았고, AI 기능과 배포 단계에서 도입을 검토 중인 스택입니다.

| 영역 | 후보 | 선정 이유 |
|---|---|---|
| OCR | PaddleOCR | 한국어 문서 인식을 지원하는 오픈소스로, 비용 절감과 커스터마이징에 유리 |
| Embedding | OpenAI `text-embedding-3-small` | 추출한 문서를 벡터로 변환해 관련 내용을 빠르게 검색 |
| LLM | **모델 확정 전** | 비용을 절감하면서 검색된 문서를 기반으로 답변 생성. 모델 ID는 도입 시점에 확정 |
| STT | OpenAI GPT-4o Transcribe | 사용자의 한국어 음성을 텍스트 질문으로 변환 |
| AI Infra | RunPod GPU | PaddleOCR와 향후 자체 운영할 무거운 AI 모델을 GPU 환경에서 실행 |
| Cache/Queue | Redis · Celery | 반복 조회 데이터를 캐싱하고 OCR·Embedding·STT 작업을 비동기로 처리 |
| Cloud | AWS S3 · EC2 | S3에 문서와 정적 파일을 저장하고, EC2에서 백엔드 서버와 AI Worker를 운영 |
| 실행 환경 | Docker | 로컬·서버의 실행 환경을 동일하게 구성 |

## 참고

- 도입이 확정되면 이 표의 항목을 `현재 사용`으로 옮기고 README 배지도 함께 갱신합니다.
- API 키·토큰 등 비밀값은 `.env`에만 두고 코드·문서·로그에 남기지 않습니다. 비밀값이 필요한 브라우저 요청은 백엔드를 경유합니다.
