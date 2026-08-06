# 필드메드 (FieldMed)

의료기기 현장 영업을 돕는 다중 에이전트 업무 자동화 시스템입니다.

- 팀: 셀럽(SalesLove)
- 슬로건: Become the Celebrity of Sales.

## 빠른 시작

필수 도구는 Git, Node 24, uv입니다. 윈도우에서는 Git Bash를 사용합니다.

```bash
bash scripts/setup.sh
bash scripts/dev.sh         # 프론트엔드 + 백엔드
bash scripts/frontend.sh    # 프론트엔드만
bash scripts/backend.sh     # 백엔드만
```

`setup.sh`는 파일이 없을 때만 각 `.env.example`을 `.env`로 복사합니다. 프론트엔드는 기본 API 주소로 실행할 수 있고, 백엔드의 DB 기능을 사용할 때 `backend/.env`의 `DATABASE_URL`을 설정합니다. 비밀값은 프론트엔드 환경변수에 넣지 않습니다.

| 서비스 | 주소 |
|---|---|
| 프론트엔드 | http://localhost:5173 |
| API 문서 | http://localhost:8000/docs |
| DB 상태 | http://localhost:8000/api/health/db |

## 문서

| 문서 | 용도 |
|---|---|
| [AGENTS.md](AGENTS.md) | 사람과 AI가 공유하는 개발 규칙 원본 |
| [프로젝트 구조](docs/project-structure.md) | 파일·폴더 배치 |
| [문서 목록](docs/README.md) | 추가 문서 안내 |
| [SQL 가이드](backend/sql/README.md) | 스키마 변경 절차 |

## 기술 스택

- Frontend: React 19, TypeScript, Vite 8, SCSS Modules, React Router 8, axios
- Backend: Python 3.13, FastAPI, uv, SQLAlchemy async, Supabase PostgreSQL
- Quality: oxlint, prettier, ruff, pytest, GitHub Actions

개발은 `<GitHub 사용자명>/<작업명> → develop → main` 순서로 PR을 통해 병합합니다.
