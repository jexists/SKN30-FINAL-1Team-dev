# 시작하기

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
