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
| 딜 팀·담당자 조건 신규 테스트 | 24 passed |
| 발주 팀·담당자 조건 신규 테스트 | 20 passed |
| C/S 팀·담당자 조건 신규 테스트 | 14 passed |
| 공용 검사(team_scope) 자체 검증 | 6 passed |
| 보고서 팀·담당자 조건 신규 테스트 | 10 passed |
| 일정 팀·담당자 조건 신규 테스트 | 14 passed |
| 고객 팀·담당자 조건 신규 테스트 | 10 passed |
| 신규 테스트 포함 전체 회귀 | 1271 passed, 3 skipped, 6 deselected (실패 0) |
| 리뷰 반영 후 전체 회귀 | 1280 passed, 2 skipped, 6 deselected (실패 0) |
| alias 판별 보완 후 딜 팀 조건 재검증 | 20 passed |
| 신규 파일 Ruff lint/format, `git diff --check` | 통과 |

전체 회귀 이후 alias 판별을 보완했으며, 영향받은 테스트 20개와 변이 검사를 다시 실행했다.
실행별 숫자는 중복된 테스트를 포함하므로 더하지 않는다.

### 기존 실패 1건 (해소)

`backend/tests/test_models.py`, `test_all_database_tables_are_mapped`:
최초 실행에서는 총합 기대값이 상수 `446`으로 박혀 있어 실제 합계 `458`과 어긋나 실패했다.
이후 `develop`에서 그 상수가 계산값 비교로 바뀌어 이 실패는 더 이상 재현되지 않는다.
`develop` 병합 후 재실행에서 실패 0을 확인했다. 이 PR 이 고친 것은 아니다.

위 표의 "실패 0"과 이 절이 서로 달라 보였던 것을 정리한 결과다.

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

## 담당자 범위 (같은 팀 안)

팀 격리가 다른 **팀**을 막는다면, 담당자 범위는 같은 팀 안에서 다른 **사람**의 자료를 막는다.
`role_code == "member"` 분기가 코드 21곳에 흩어져 있는데 검증이 없었다.

검사 방향이 팀 격리와 반대다. 팀 조건은 팀원·팀장 **모두에게** 있어야 하지만, 담당자 조건은
**팀원에게만** 있어야 한다. 팀장에게도 걸리면 팀 전체를 보지 못해 관리 화면이 비어 보인다.
그래서 자원마다 "팀원이면 있다"와 "팀장이면 없다"를 함께 본다.

컬럼 이름이 자원마다 다르다.

| 자원 | 담당자 컬럼 | 구조 |
|---|---|---|
| 딜 | `SalesDeal.owner_member_id` | 최상위 AND |
| 일정 | `Activity.owner_member_id` | 최상위 AND |
| 발주 | `_sales_deal.owner_member_id` | 발주에 담당자 컬럼이 없어 딸린 딜로 좁힌다 |
| C/S | `SupportRequest.assignee_member_id` | 접수자가 아니라 처리할 사람 |
| 보고서 | `Report.author_member_id` | 받는 사람이 아니라 쓴 사람 |
| 고객 | `CustomerContact.owner_member_id` | 담당자가 별도 표라 대표 담당자 비교와 담당자 표 EXISTS 를 `or_` 로 묶는다 |

고객만 구조가 다르다. `customers._assigned_to` 가 대표 담당자가 아니어도 담당자로 지정됐으면
자기 고객으로 보기 때문이다. 최상위 `OR` 의 **양쪽을 모두** 본다. 앞쪽 대표 담당자 비교는
`has_owner_predicate` 로, 뒤쪽 `EXISTS` 안의 `CustomerContactAssignee.member_id` 바인딩은
`has_exists_bound_predicate` 로 확인한다.

서브쿼리 안 조건은 보통 바깥 행을 거르지 못해 세지 않지만, 이 `EXISTS` 는 최상위 `OR` 의
한쪽이라 바깥 행을 실제로 거른다. 앞쪽만 보면 뒤쪽 바인딩이 인증된 사용자에서 풀려도 통과한다.

`team_scope.has_owner_predicate` 는 팀 격리와 같은 판별을 쓴다(`has_bound_predicate`).
컬럼과 묶인 값만 다르다.

팀장 검사는 값을 지정하지 않는 `narrows_to_single_owner` 를 쓴다. 팀장 본인 id 로만 확인하면
쿼리가 다른 값으로 좁혀졌을 때 통과하기 때문이다. 이 검사는 담당자 필터가 없는 요청에만 쓴다.
팀장이 화면에서 담당자를 골라 보낸 조건은 정상이며 여기서 구분하지 않는다.

팀장은 상세뿐 아니라 목록도 본다. 여섯 자원 모두 상세와 목록을 함께 검사한다.

### 담당자 범위 변이 검사

`role_code == "member"` 분기의 담당자 조건을 임시 복사본에서 모두 무력화했다. `if` 블록이
비면 구문이 깨지므로 `append(...)` 를 `pass` 로 바꿔 분기는 남기고 조건만 없앴다.

| 변이 | 결과 |
|---|---|
| 6개 자원 담당자 조건 13곳 무력화 | 12 failed, 72 passed: 여섯 자원 모두 회귀 탐지 |

리뷰 반영으로 검사를 두 가지 늘렸고, 각각에 대응하는 변이를 따로 확인했다.

| 변이 | 결과 |
|---|---|
| 고객 `EXISTS` 안 `member_id` 바인딩을 인증 사용자에서 고정값으로 교체 | 2 failed, 8 passed: 신규 `EXISTS` 검사 2개가 탐지 |
| 일정 담당자 조건을 팀장에게도 걸되 값은 제3자 id 로 교체 | 4 failed, 10 passed: 팀장 상세·목록 검사가 탐지 |

두 번째 변이는 값 기준 검사(`has_owner_predicate`)로는 잡히지 않는다. 팀장 본인 id 와
비교하므로 다른 값에 묶인 조건을 통과시킨다. `narrows_to_single_owner` 가 그 자리를 메운다.

원본에는 변이를 적용하지 않았고, 검사 후 복원과 `git status` 무변경을 확인했다.

### 쿼리 조건이 아닌 세 곳은 이미 덮여 있었다

`role_code == "member"` 분기 21곳 중 세 곳은 WHERE 조건이 아니라 응답으로 막는다. 이 방식은
쿼리를 들여다볼 필요가 없어, 호출해서 나오는 상태 코드로 확인한다. 확인해 보니 셋 다 기존
테스트가 이미 덮고 있어 이번에 추가하지 않았다.

| 위치 | 막는 것 | 덮는 기존 테스트 |
|---|---|---|
| `contract_suggestions.py` | 남의 딜에 달린 제안 무시 → 404 | `test_dismiss_hides_other_owners_suggestion_as_not_found` (저장이 일어나지 않은 것까지 확인) |
| `sales_deals.py` `_team_contact` | 남의 고객을 내 딜에 붙이기 → 422 | `test_sales_deals.py` 의 `contact_owner_mismatch` 검증 (팀장은 통과하는 것도 함께 확인) |
| `dashboard.py` | 팀원이 남의 실적 조회 → 403 | `test_member_cannot_widen_owner_scope` |

`sales_deals.py` 쪽은 쓰기 경로다. 읽기와 달리 남의 고객을 자기 딜에 끌어다 붙이는 문제라
따로 확인이 필요한데, 기존 테스트가 팀원 거부와 팀장 허용을 함께 보고 있다.

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
