# 로컬 테스트 DB

2026-09-07, 이 작업 머신에 PostgreSQL 17.11 테스트 인스턴스를 구성했다.

| 항목 | 설정 |
|---|---|
| 주소 | `127.0.0.1:55432` (로컬 전용) |
| DB / 접속 역할 | `salesluv_test` / `salesluv_test` |
| 접속 설정 | `backend/.env.test` (권한 0600, Git 제외) |
| 데이터·로그 | `backend/.postgres-test.local/` (Git 제외) |
| PostgreSQL 도구 | `/usr/local/opt/postgresql@17/bin/` |
| 시작 방식 | 수동 실행. 로그인 시 자동 시작은 설정하지 않음 |

저장소 `backend/sql/*.sql` 38개를 파일명 순서로 적용했다. 적용 파일명과 SHA-256은
DB의 `test_meta.migrations`에 기록되어 있다. 고객·영업 원본 데이터는 복사하지 않았다.
Supabase Auth 자체는 설치하지 않고, `member.id` 외래키에 필요한 `auth.users(id uuid)`만 만들었다.
따라서 Supabase 로그인·토큰 발급·Storage 테스트용 환경은 아니다.

접속 역할은 SUPERUSER/CREATEDB/CREATEROLE 없이 public/auth 데이터 접근 권한과 BYPASSRLS를 가진다.
baseline은 RLS를 켜고 클라이언트 정책을 만들지 않으므로, 백엔드 직접 연결을 모사하기 위한 설정이다.
팀 격리는 API 쿼리에서 검증한다. 이 환경의 통과를 클라이언트용 RLS 정책 검증으로 해석하지 않는다.

## 실행

저장소 루트에서 시작/상태 확인/중지한다. 데이터 디렉터리는 중지해도 유지된다.

```sh
/usr/local/opt/postgresql@17/bin/pg_ctl -D backend/.postgres-test.local/data -l backend/.postgres-test.local/server.log -w start
/usr/local/opt/postgresql@17/bin/pg_ctl -D backend/.postgres-test.local/data status
/usr/local/opt/postgresql@17/bin/pg_ctl -D backend/.postgres-test.local/data -m fast -w stop
```

재부팅 등으로 `/tmp/salesluv-test-132-501` 소켓 디렉터리가 없어졌다면 같은 사용자로
`mkdir -m 700 /tmp/salesluv-test-132-501` 후 시작한다. 이 경로의 501은 이 머신의 사용자 ID다.
Homebrew의 기본 클러스터와 별도로 만든 인스턴스이므로 `brew services start` 대신 위 명령을 쓴다.

`backend`에서 명시적으로 테스트 설정을 읽는다. 앱의 일반 `.env`는 생성하거나 덮어쓰지 않았다.

```sh
uv run --no-sync --env-file .env.test env RUN_INTEGRATION_TESTS=true pytest tests/test_local_database.py -q
uv run --no-sync --env-file .env.test env RUN_INTEGRATION_TESTS=true pytest tests/test_health.py -q
```

## 확인 결과

- API health / DB health / legacy migration 쿼리 검사: 3개 통과.
- `test_local_database.py`: 1개 통과. 실제 고객사 API에서 A팀 생성·본인 조회 성공,
  B팀 조회/수정 404, 목록에서 B팀 제외, 요청 종료 후 새 세션에서 저장 유지와 B팀 데이터 보존 확인.
- 두 고객사 행을 실제 flush한 후 예외를 발생시켜, 새 세션에서 두 행 모두 원상복구된 것을 확인.
  이는 DB 트랜잭션 smoke이며 발주·보고서의 다중 테이블 API 원자성 검증은 아직 아니다.
- 인증 의존성은 합성 팀장 객체로 대체했다. SQL 실행과 API 직렬화, 요청별 DB 세션은 실제다.
- 테스트가 만든 A/B팀·고객사는 finally에서 해당 UUID 범위만 삭제하며 정리 완료를 확인한다.
- 신규 테스트 lint/format 통과. 로컬 DB와 설정의 Git 제외 확인.

## 남은 스키마 차이

`tests/test_models.py::test_models_match_configured_database`는 실패했다.
SQL에 존재하는 `agent_run.apply_status`, `base_report_version`, `base_generation_input_version`이
현재 모델과 legacy 허용 목록에는 없다. 검사에서 처음 발견된 차이이며, 추가 차이가 없다는 뜻은 아니다.
기존 SQL이나 모델을 임의로 바꾸지 않았다. DB 연결·고객사 smoke는 사용 가능하지만 전체 스키마
일치 검증은 완료되지 않았다.

그 외 딜·일정·보고서·발주·C/S의 실데이터 격리와 각 API의 실패 주입 검증은 후속 작업이다.
