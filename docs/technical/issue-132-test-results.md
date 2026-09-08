# Issue #132 테스트 실행 기록

> 이후 로컬 PostgreSQL 테스트 DB를 구축했다. DB 부재에 관한 아래 기록은 최초 실행 시점의
> 상태이며, 최신 구축·실데이터 smoke 결과는 [로컬 테스트 DB](local-test-database.md)를 참고한다.

- 실행일: 2026-09-07
- 이슈: https://github.com/jexists/SKN30-FINAL-1Team-dev/issues/132
- 브랜치: `jiyu-park/team-isolation-tests`
- 기준 HEAD: `7130980`
- 이번 추가: `team_scope.py`(공용 검사)와 그 자체를 검증하는 `test_team_scope.py` 6개,
  `test_deal_team_predicates.py` 20개,
  `test_order_team_predicates.py` 16개, `test_support_team_predicates.py` 10개,
  `test_production_security.py` 11개, `test_local_database.py` 1개.
- 정리한 것: `backend/tests/test_sales_deals.py`에 먼저 넣었던 팀 격리 테스트 3개를 지웠다.
  SQL 문자열에서 팀 조건 이름을 찾는 방식이라 조인 조건·서브쿼리 WHERE 를 잘못 집었고,
  실제로 팀 필터를 제거해도 통과하는 것을 확인했다. 같은 범위를 `test_deal_team_predicates.py`
  20개가 표현식 트리로 더 촘촘히 덮는다.
- 검사 방식을 한 곳으로 모았다: 딜 파일 안에만 있던 판별을 `tests/team_scope.py`로 빼고
  딜·발주·C/S 세 파일이 같은 함수를 쓴다.
- 결론: 실행 가능한 단위/HTTP 대역 회귀 검증을 수행했으나, 실제 DB 검증이 남아 이슈 완료는 아니다.

## 실행 결과

| 실행 | 결과 |
|---|---|
| 고객·딜·일정·발주·C/S·보고서·보고서 검토·인증 8개 테스트 파일 | 252 passed |
| 추가 전 전체 회귀 (`-m 'not integration'`) | 1167 passed, 1 failed, 3 skipped, 5 deselected |
| production 앱 초기화 신규 테스트 | 11 passed |
| 딜 팀 조건 신규 테스트 | 20 passed |
| 발주 팀 조건 신규 테스트 | 16 passed |
| C/S 팀 조건 신규 테스트 | 10 passed |
| 공용 검사(team_scope) 자체 검증 | 6 passed |
| 신규 테스트 포함 전체 회귀 | 1221 passed, 1 failed, 3 skipped, 6 deselected |
| alias 판별 보완 후 딜 팀 조건 재검증 | 20 passed |
| 신규 파일 Ruff lint/format, `git diff --check` | 통과 |

전체 회귀 이후 alias 판별을 보완했으며, 영향받은 테스트 20개와 변이 검사를 다시 실행했다.
실행별 숫자는 중복된 테스트를 포함하므로 더하지 않는다.

### 기존 실패 1건

`backend/tests/test_models.py:127`, `test_all_database_tables_are_mapped`:
모델별 `EXPECTED_COLUMN_COUNTS` 비교는 통과하지만, 별도의 총합 상수 `446`과 실제 합계 `458`이 다르다.
신규 테스트 추가 전에도 동일하게 실패했다. 모델 매핑 테스트의 총합 기대값 불일치이며,
실제 DB 스키마 일치 여부를 판정한 결과는 아니다. 이번 실행에서는 기존 테스트를 변경하지 않았다.

### 실제 DB 관련 미실행

- 모델과 DB 스키마 비교, DB health, legacy report migration 쿼리: DB 설정 부재로 3개 skip.
- `integration` marker의 5개 테스트: 이번 외부 연결 없는 실행에서 제외.
- 6개 주요 리소스의 A/B팀 실데이터 접근, 타 팀 FK 주입, 별도 세션의 저장 영속성,
  실패 주입 후 실제 DB 전체 롤백은 미실행.
- 루트 `.env`, `backend/.env`, `backend/.env.test`가 없고, 프로세스 `DATABASE_URL` 및
  `TEST_DATABASE_URL`도 미설정이다. PATH에서 PostgreSQL/Docker 실행 파일을 찾지 못했다.
- 테스트용 PostgreSQL과 합성 데이터 구성이 다음 선행 작업이다. 운영/공유 DB 데이터는 변경하지 않았다.

## 이번에 추가한 보장

### 딜 SQL 팀 조건 20개

- 팀원/팀장 각각에 대해 상세 조회가 실행한 WHERE에서 딜·담당자·고객사·파이프라인·딜 유형·상품·
  견적 상태·계약 상태·연락처 담당자의 팀 컬럼과 인증된 팀 ID 바인딩을 검사한다: 18개.
- 팀원/팀장 각각의 빈 목록에서 total, 본문, 탭 집계 3개 쿼리에 팀 조건이 존재하는지 검사한다: 2개.
- 기존처럼 SQL 문자열의 팀 조건 개수만 세지 않고, SQLAlchemy 표현식의 alias 대상과 바인딩을 검사한다.
- 빈 목록은 자식 조회를 생략한다. 품목·참여자·발주 상태의 실제 반환 데이터 검증을 대신하지 않는다.
- 가짜 DB를 사용하므로 실데이터 누출 차단과 쓰기 권한의 최종 증거는 아니다.

임시 복사본에서 실제 코드 조건을 제거한 변이 검사:

| 변이 | 보완 후 결과 |
|---|---|
| 딜 자체 `team_id` 조건 제거 | 4 failed, 16 passed: 회귀 탐지 |
| 조인 담당자 `team_id` 조건 제거 | 2 failed, 18 passed: 회귀 탐지 |

초기 검사에서는 같은 Member 모델의 서로 다른 alias를 구분하지 못해 담당자 조건 제거가 통과했다.
alias 테이블 동일성 검사를 추가한 뒤 위 실패를 확인했다. 원본 애플리케이션에는 변이를 적용하지 않았다.

### 발주 SQL 팀 조건 16개

- 팀원/팀장 각각에 대해 상세 조회가 실행한 WHERE에서 발주·딜·담당자·고객사·발주 상태·등록자·
  입고처의 팀 컬럼과 인증된 팀 ID 바인딩을 검사한다: 14개.
- 팀원/팀장 각각의 빈 목록에서 total, 본문, 상태별 건수, 공급처 목록 4개 쿼리에 팀 조건이
  존재하는지 검사한다: 2개. 공급처 목록은 필터 후보라 여기서 새면 남의 팀 거래처 이름이 보인다.

### C/S SQL 팀 조건 10개

- 팀원/팀장 각각에 대해 상세 조회가 실행한 WHERE에서 요청·담당자·고객사·딜의 팀 컬럼과
  인증된 팀 ID 바인딩을 검사한다: 8개.
- 팀원/팀장 각각의 빈 목록에서 total, 본문, 상태별 건수 3개 쿼리를 검사한다: 2개.

### 공용 검사의 범위 (리뷰 반영)

첫 구현은 `visitors.iterate` 로 WHERE 아래를 끝까지 훑어, 조건 하나만 찾으면 통과시켰다.
서브쿼리 안에만 팀 조건이 있고 바깥 행은 전혀 안 막히는 쿼리도 통과하는 것을 확인했다.

바깥 행을 거르는 자리만 보도록 순회를 좁혔다. `AND` 와 `OR`, 그리고 `AND` 안의 `OR` 를
감싸는 괄호(`Grouping`)는 따라 내려가고, 서브쿼리 안으로는 들어가지 않는다. `OR` 를 막으면
실제 스코프의 nullable 관계(`or_(fk.is_(None), <표>.team_id == member.team_id)`)를 쓰는
상품·견적 상태·계약 상태·연락처 담당자를 검사할 수 없어 그대로 둔다.

`test_team_scope.py` 6개가 이 경계를 고정한다: 최상위·`AND`·nullable `OR` 는 통과,
서브쿼리 전용·다른 팀 값·`WHERE` 없음은 불통과.

### 세 자원 동시 변이 검사

`sales_deals.py`·`orders.py`·`support.py`의 자기 테이블 팀 조건을 임시 복사본에서 모두 제거하고
세 파일을 함께 실행했다.

| 변이 | 결과 |
|---|---|
| 딜 5개 · 발주 3개 · C/S 1개 조건 동시 제거 | 12 failed, 34 passed: 세 자원 모두 회귀 탐지 |

원본 애플리케이션에는 변이를 적용하지 않았고, 검사 후 복원과 `git diff` 무변경을 확인했다.

### Production 초기화 11개

부모 프로세스의 비밀값을 전달하지 않고 `.env` 없는 임시 디렉터리의 별도 Python 프로세스에서
`app.main`을 import했다. HTTP 서버를 띄우거나 외부 서비스를 연결한 검증은 아니다.

- 차단 10개: DEBUG=true, 빈 CORS, 공백 CORS, HTTP, path, query, fragment,
  사용자 정보 포함 origin, 정상/HTTP 혼합 origin, wildcard.
- 정상 1개: 복수 HTTPS origin에서 앱 import 성공 및 production secure-cookie 설정 확인.
- 단순 비정상 종료뿐 아니라 해당 설정 검증 오류와 성공 표식 부재를 확인했다.

## flush/commit 정적 점검

API 계층 AST에서 `flush()` 40개 호출 지점을 확인했다. 같은 함수 안에 직접 commit이 없는 항목은:

| 함수 | commit 책임 |
|---|---|
| `admin._resolve_team` | 호출자 `create_account`의 flush/commit |
| `customers._bulk_company` | 호출자 `create_customer_contacts_bulk` → `_flush_and_commit` |
| `customers.create_customer_contacts_bulk` | `_flush_and_commit` |
| `reports._replace_report_deals` | 호출자 `finalize_report`의 commit |

나머지 flush 포함 함수에는 직접 commit 호출이 존재했다. 이것은 호출 위치와 상위 책임을 확인한
정적 결과이며, 모든 분기의 저장 성공이나 DB 원자성을 입증하지 않는다. 새 DB 세션 재조회가 남아 있다.

## 재현 명령

`backend` 디렉터리에서 실행한다. CI(`.github/workflows/ci-backend.yml`)와 같은 `uv` 를 쓴다.

```sh
APP_ENV=test DATABASE_URL='' RUN_INTEGRATION_TESTS=false uv run pytest -q -m 'not integration' --junitxml=/tmp/issue132-final.xml
APP_ENV=test DATABASE_URL='' uv run pytest tests/team_scope.py tests/test_team_scope.py tests/test_deal_team_predicates.py tests/test_order_team_predicates.py tests/test_support_team_predicates.py tests/test_production_security.py tests/test_local_database.py -q
uv run ruff check tests/team_scope.py tests/test_team_scope.py tests/test_deal_team_predicates.py tests/test_order_team_predicates.py tests/test_support_team_predicates.py tests/test_production_security.py tests/test_local_database.py
uv run ruff format --check tests/team_scope.py tests/test_team_scope.py tests/test_deal_team_predicates.py tests/test_order_team_predicates.py tests/test_support_team_predicates.py tests/test_production_security.py tests/test_local_database.py
git -C .. diff --check
```

실행 시 생성한 로컬 임시 증적: `/tmp/issue132-targeted.xml`, `/tmp/issue132-regression.xml`,
`/tmp/issue132-production.xml`, `/tmp/issue132-predicates.xml`, `/tmp/issue132-final.xml`,
`/tmp/issue132-mutations.json`. 임시 파일은 OS 정리 시 없어질 수 있다.
