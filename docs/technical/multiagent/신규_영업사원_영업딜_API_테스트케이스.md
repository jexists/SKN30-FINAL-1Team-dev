# 신규 영업사원 계정·영업 딜·일정·보고서 API 테스트 케이스

## 1. 테스트 목표

실제 사용자 흐름에 맞춰 다음 과정을 검증한다.

1. 관리자가 기존 팀에 신규 영업사원 계정을 발급한다.
2. 신규 영업사원이 자신의 계정으로 로그인한다.
3. 신규 영업사원이 고객사 담당자를 등록한다.
4. 테스트 팀장이 딜 생성에 사용할 제품을 준비한다.
5. 신규 영업사원이 제품과 영업 단계를 선택해 영업 딜을 생성한다.
6. 생성한 딜이 신규 영업사원 소유로 조회되는지 확인한다.
7. 생성한 딜에 연결된 일정을 등록하고 미팅 보고서를 작성·확정한다.
8. 보고서 확정으로 생성된 AI 추천 일정 카드가 캘린더에 표시되는지 확인한다.
9. 추천 일정을 캘린더에 등록하고 해당 일정의 AI 브리핑을 확인한다.
10. 같은 딜의 일정을 캘린더에서 수동으로 등록하고 AI 브리핑을 확인한다.

이 테스트는 로컬 백엔드를 통해 실제 Supabase Auth·원격 DB·실제 LLM을 사용한다. 신규 계정,
제품, 고객사 담당자, 영업 딜, 일정, 보고서, AgentRun은 자동 롤백되지 않는다.

## 2. 현재 확인된 전제조건

| 항목 | 현재 값 |
|---|---|
| 실행 환경 | `local` |
| 기존 테스트 계정 | `bak3036@gmail.com` |
| 기존 테스트 계정 역할 | `member` |
| 기존 테스트 계정의 관리자 권한 | 없음 |
| 기존 테스트 계정 ID | `c3ad2e8c-2d70-4bd2-a10f-bf1d0a082947` |
| 기존 팀 ID | `a71b1b30-7b2f-4be1-9e32-e2e2f647e3c4` |
| 테스트 고객사 ID | `759ac0ae-f2ff-4fcb-a60f-a016803de9d3` |
| 테스트 제품 ID | `6c39be91-2c1e-5c67-bdd3-0a57fb431859` |
| 기본 파이프라인 ID | `7a9df25e-f40b-02ff-2452-c2b9a63849ef` |
| 첫 파이프라인 단계 ID | `414ab196-22e9-77f0-6ddc-1ac00cdb9d9e` |
| 영업 유형 코드 | `new_installation` |

`bak3036@gmail.com`으로 바로 신규 계정을 만들 수는 없다. 계정 발급 API는 `ADMIN_USER_IDS`에 등록된 관리자만 사용할 수 있다.

## 3. 관리자 준비 방법

다음 중 한 가지가 필요하다.

### 방법 A — 이미 등록된 관리자 계정 사용

`ADMIN_USER_IDS`에 등록된 관리자 계정의 이메일과 비밀번호로 로그인한다. 이 방법을 권장한다.

### 방법 B — 로컬에서 기존 테스트 계정을 임시 관리자로 허용

`backend/.env`의 `ADMIN_USER_IDS`에 아래 구성원 ID를 쉼표로 추가하고 백엔드를 재시작한다.

```text
c3ad2e8c-2d70-4bd2-a10f-bf1d0a082947
```

기존 값이 있으면 덮어쓰지 말고 다음 형태로 추가한다.

```text
ADMIN_USER_IDS=기존_ID,c3ad2e8c-2d70-4bd2-a10f-bf1d0a082947
```

이 설정은 `APP_ENV=local`인 로컬 테스트 환경에서만 사용한다. 변경 후 백엔드를 반드시 다시 시작해야 한다.

## 4. 사용자 흐름 기준 테스트 케이스

### TC-01 — 일반 영업사원은 신규 계정을 발급할 수 없다

| 구분 | 내용 |
|---|---|
| 행위자 | 기존 일반 영업사원 |
| 사전조건 | `bak3036@gmail.com`이 `ADMIN_USER_IDS`에 없음 |
| 행동 | 신규 계정 발급 API 호출 |
| 기대 결과 | HTTP `403`, `admin_only` |
| 목적 | 일반 사용자의 계정 발급 권한 차단 확인 |

### TC-02 — 관리자가 기존 팀에 신규 영업사원을 발급한다

| 구분 | 내용 |
|---|---|
| 행위자 | 관리자 |
| 사전조건 | 관리자 로그인, `APP_ENV=local` |
| 행동 | 기존 팀, 역할 `member`, 바로 만들기로 계정 발급 |
| 기대 결과 | HTTP `201`, 신규 구성원 ID 반환 |
| 추가 확인 | 신규 구성원의 `team_id`, `role_code`, `region_code` 확인 |

### TC-03 — 같은 이메일로 계정을 중복 발급할 수 없다

| 구분 | 내용 |
|---|---|
| 행위자 | 관리자 |
| 사전조건 | TC-02에서 계정 생성 완료 |
| 행동 | 같은 이메일로 다시 계정 발급 |
| 기대 결과 | HTTP `409`, `email_already_exists` |

### TC-04 — 신규 영업사원이 자신의 계정으로 로그인한다

| 구분 | 내용 |
|---|---|
| 행위자 | 신규 영업사원 |
| 사전조건 | TC-02 성공 |
| 행동 | 신규 이메일과 로컬 바로 만들기 비밀번호로 로그인 |
| 기대 결과 | HTTP `200`, `role_code=member`, 기존 팀 ID 반환 |

### TC-05 — 신규 영업사원이 고객사 담당자를 등록한다

| 구분 | 내용 |
|---|---|
| 행위자 | 신규 영업사원 |
| 사전조건 | TC-04 성공 |
| 행동 | 테스트 고객사에 신규 담당자 등록 |
| 기대 결과 | HTTP `201`, 담당자 ID 반환 |
| 추가 확인 | 담당자 소유자가 신규 영업사원 ID인지 확인 |

### TC-05.5 — 관리자가 테스트 팀에 제품을 등록한다

| 구분 | 내용 |
|---|---|
| 행위자 | 테스트 팀장(`role_code=manager`) |
| 사전조건 | TC-02의 대상 팀에 활성 팀장 계정 존재 |
| 행동 | 상품 관리 화면에서 TC-06에 사용할 테스트 제품 등록 |
| 기대 결과 | HTTP `201`, 활성 제품 ID 반환 |
| 추가 확인 | 신규 영업사원의 제품 검색 결과에 등록한 제품이 표시됨 |
| 주의 | `is_admin=true`인 시스템 관리자라도 팀 역할이 `member`이면 제품을 등록할 수 없음 |

### TC-06 — 신규 영업사원이 영업 딜을 생성한다

| 구분 | 내용 |
|---|---|
| 행위자 | 신규 영업사원 |
| 사전조건 | TC-05 성공, 제품·파이프라인 설정 존재 |
| 행동 | 고객사, 담당자, 제품, 영업 단계를 선택해 딜 생성 |
| 기대 결과 | HTTP `201`, 영업 딜 ID 반환 |
| 추가 확인 | 딜의 고객사·담당자·제품·단계가 요청과 일치 |

### TC-07 — 신규 영업사원이 생성한 딜을 다시 조회한다

| 구분 | 내용 |
|---|---|
| 행위자 | 신규 영업사원 |
| 사전조건 | TC-06 성공 |
| 행동 | 생성된 딜 ID로 상세 조회 |
| 기대 결과 | HTTP `200`, 생성한 딜 정보 반환 |

### TC-08 — 다른 고객사 소속 담당자로 딜을 만들 수 없다

| 구분 | 내용 |
|---|---|
| 행위자 | 신규 영업사원 |
| 사전조건 | 서로 다른 고객사와 담당자 준비 |
| 행동 | 고객사와 소속이 다른 담당자 ID로 딜 생성 |
| 기대 결과 | HTTP `422`, `contact_company_mismatch` |

### TC-09 — 신규 영업사원이 영업 딜에 연결된 일정을 추가한다

| 구분 | 내용 |
|---|---|
| 행위자 | 신규 영업사원 |
| 사전조건 | TC-06 성공, 팀의 미팅 분류 설정 존재 |
| 행동 | 캘린더에서 고객사·담당자·영업 딜을 선택해 미팅 일정 등록 |
| 기대 결과 | HTTP `201`, 일정 ID 반환 |
| 추가 확인 | 일정의 소유자·고객사·담당자·딜·제품이 TC-06 결과와 일치 |

### TC-10 — 신규 영업사원이 등록한 일정의 미팅 보고서를 작성·확정한다

| 구분 | 내용 |
|---|---|
| 행위자 | 신규 영업사원 |
| 사전조건 | TC-09 성공, LLM 설정 완료 |
| 행동 | 일정 상세에서 보고서 작성 화면을 열고 미팅 원문 입력, AI 초안 생성 후 확정 |
| 기대 결과 | 보고서 생성 AgentRun 완료, `POST /reports/finalize` HTTP `201` |
| 추가 확인 | 보고서가 `submitted`, 작성자와 `source_activity_id`가 현재 사용자·일정과 일치 |

### TC-11 — 캘린더 추천 일정 목록에 일정 카드 한 개가 표시된다

| 구분 | 내용 |
|---|---|
| 행위자 | 신규 영업사원 |
| 사전조건 | TC-10 보고서 확정 후 계약관리→일정관리 백그라운드 실행 완료 |
| 행동 | 캘린더 화면에 다시 진입해 `AI 추천 일정` 패널 확인 |
| 기대 결과 | 현재 영업 딜의 추천 카드가 정확히 1개 표시됨 |
| 추가 확인 | 카드에 고객사·담당자·추천 사유·후보 날짜와 시간이 표시됨 |

### TC-12 — 신규 영업사원이 추천 일정을 캘린더에 등록한다

| 구분 | 내용 |
|---|---|
| 행위자 | 신규 영업사원 |
| 사전조건 | TC-11 성공, 추천 카드에 일정 후보가 한 개 이상 존재 |
| 행동 | 추천 카드의 후보를 선택하고 `추천일에 넣기` 클릭 |
| 기대 결과 | HTTP `201`, 추천 후보 시간으로 일정 생성 |
| 추가 확인 | 요청에 `schedule_management_run_id`가 포함되고 추천 상태가 `accepted`로 변경 |

### TC-13 — 신규 영업사원이 캘린더에서 일정을 수동 등록한다

| 구분 | 내용 |
|---|---|
| 행위자 | 신규 영업사원 |
| 사전조건 | TC-06 성공, 추천 일정과 겹치지 않는 날짜·시간 준비 |
| 행동 | 캘린더 빈 날짜 또는 `일정 추가`에서 고객사·담당자·영업 딜을 직접 선택해 등록 |
| 기대 결과 | HTTP `201`, 수동 일정 ID 반환 |
| 추가 확인 | 요청의 `schedule_management_run_id`가 `null`이고 일정 정보가 입력값과 일치 |

### TC-14 — 캘린더 일정 상세에서 AI 브리핑을 확인한다

| 구분 | 내용 |
|---|---|
| 행위자 | 신규 영업사원 |
| 사전조건 | TC-12·TC-13 일정 등록 후 `contract_management_briefing` 완료 |
| 행동 | 캘린더에 등록된 추천 일정과 수동 일정을 각각 클릭 |
| 기대 결과 | 일정 상세의 `AI 브리핑`에 핵심 하이라이트·추천 행동·부족 정보 표시 |
| 추가 확인 | `GET /activities/{activity_id}`의 `ai_briefing`이 `null`이 아니며 두 일정 ID가 서로 다름 |

## 5. API 통합 테스트 실행

### 5.1 공통 변수

```bash
API="http://127.0.0.1:8000/api"
ORIGIN="http://localhost:5173"

ADMIN_EMAIL="bak3036@gmail.com"
TEAM_ID="a71b1b30-7b2f-4be1-9e32-e2e2f647e3c4"
COMPANY_ID="759ac0ae-f2ff-4fcb-a60f-a016803de9d3"
PRODUCT_ID="6c39be91-2c1e-5c67-bdd3-0a57fb431859"
PIPELINE_ID="7a9df25e-f40b-02ff-2452-c2b9a63849ef"
STAGE_ID="414ab196-22e9-77f0-6ddc-1ac00cdb9d9e"
DEAL_TYPE_CODE="new_installation"

RUN_TAG="$(date +%Y%m%d%H%M%S)"
NEW_SALES_EMAIL="salesperson.api.${RUN_TAG}@example.com"
NEW_SALES_NAME="API 영업사원 ${RUN_TAG}"
TEST_PRODUCT_NAME="TC-06 테스트 제품 ${RUN_TAG}"

ADMIN_COOKIE_JAR="$(mktemp -t salesluv-admin-cookies)"
TEAM_MANAGER_COOKIE_JAR="$(mktemp -t salesluv-manager-cookies)"
SALES_COOKIE_JAR="$(mktemp -t salesluv-sales-cookies)"
```

신규 이메일에는 실행 시각이 포함되므로 계정 중복을 피할 수 있다.

### 5.2 관리자 로그인

다음 명령을 실행하고 관리자 계정 비밀번호를 입력한다.

```bash
printf "관리자 계정 비밀번호를 입력하고 Enter를 누르세요: "
read -s ADMIN_PASSWORD
printf "\n"
```

```bash
ADMIN_LOGIN_RESPONSE="$(
  jq -n \
    --arg email "$ADMIN_EMAIL" \
    --arg password "$ADMIN_PASSWORD" \
    '{email:$email,password:$password}' |
  curl -sS \
    -c "$ADMIN_COOKIE_JAR" \
    -H "Origin: $ORIGIN" \
    -H "Content-Type: application/json" \
    --data-binary @- \
    "$API/auth/login"
)"

echo "$ADMIN_LOGIN_RESPONSE" | jq
unset ADMIN_PASSWORD
```

관리자 권한을 확인한다.

```bash
ADMIN_ME_RESPONSE="$(curl -sS -b "$ADMIN_COOKIE_JAR" "$API/auth/me")"
echo "$ADMIN_ME_RESPONSE" | jq '{id, email, display_name, role_code, team_id, is_admin}'
```

통과 기준:

```json
{
  "is_admin": true
}
```

`is_admin`이 `false`라면 계정 발급 단계로 진행하지 않는다. 3장의 관리자 준비를 먼저 완료한다.

### 5.3 신규 영업사원 계정 발급

사용자 화면 흐름:

1. 관리자가 계정 발급 화면에 들어간다.
2. 기존 팀을 선택한다.
3. 이메일과 이름을 입력한다.
4. 역할에서 `팀원`을 선택한다.
5. 담당지역에서 `부산`을 선택한다.
6. 로컬 발급 방식에서 `바로 만들기`를 선택한다.
7. `계정 발급`을 누른다.

API 입력:

```json
{
  "email": "실행 시각을 포함한 신규 이메일",
  "display_name": "실행 시각을 포함한 API 영업사원 이름",
  "role_code": "member",
  "region_code": "busan",
  "team_id": "a71b1b30-7b2f-4be1-9e32-e2e2f647e3c4",
  "instant": true
}
```

실행 명령:

```bash
ACCOUNT_RESPONSE="$(
  jq -n \
    --arg email "$NEW_SALES_EMAIL" \
    --arg display_name "$NEW_SALES_NAME" \
    --arg team_id "$TEAM_ID" \
    '{
      email:$email,
      display_name:$display_name,
      role_code:"member",
      region_code:"busan",
      team_id:$team_id,
      instant:true
    }' |
  curl -sS \
    -b "$ADMIN_COOKIE_JAR" \
    -H "Origin: $ORIGIN" \
    -H "Content-Type: application/json" \
    --data-binary @- \
    "$API/admin/accounts"
)"

echo "$ACCOUNT_RESPONSE" |
jq '{id, team_id, display_name, email, role_code, region_code, detail}'

NEW_SALES_MEMBER_ID="$(echo "$ACCOUNT_RESPONSE" | jq -r '.id // empty')"
echo "NEW_SALES_EMAIL=$NEW_SALES_EMAIL"
echo "NEW_SALES_MEMBER_ID=$NEW_SALES_MEMBER_ID"
```

통과 기준:

- `NEW_SALES_MEMBER_ID`가 비어 있지 않다.
- `team_id`가 `a71b1b30-7b2f-4be1-9e32-e2e2f647e3c4`다.
- `role_code`가 `member`다.
- `region_code`가 `busan`이다.

### 5.4 중복 계정 발급 차단 확인

TC-03을 확인할 때만 실행한다.

```bash
jq -n \
  --arg email "$NEW_SALES_EMAIL" \
  --arg display_name "$NEW_SALES_NAME" \
  --arg team_id "$TEAM_ID" \
  '{
    email:$email,
    display_name:$display_name,
    role_code:"member",
    region_code:"busan",
    team_id:$team_id,
    instant:true
  }' |
curl -sS \
  -b "$ADMIN_COOKIE_JAR" \
  -H "Origin: $ORIGIN" \
  -H "Content-Type: application/json" \
  --data-binary @- \
  "$API/admin/accounts" |
jq
```

기대 결과:

```json
{
  "detail": "email_already_exists"
}
```

### 5.5 신규 영업사원 로그인

로컬 `바로 만들기`에서 사용하는 개발용 비밀번호를 입력한다.

```bash
printf "신규 영업사원 로컬 개발 비밀번호를 입력하고 Enter를 누르세요: "
read -s NEW_SALES_PASSWORD
printf "\n"
```

```bash
SALES_LOGIN_RESPONSE="$(
  jq -n \
    --arg email "$NEW_SALES_EMAIL" \
    --arg password "$NEW_SALES_PASSWORD" \
    '{email:$email,password:$password}' |
  curl -sS \
    -c "$SALES_COOKIE_JAR" \
    -H "Origin: $ORIGIN" \
    -H "Content-Type: application/json" \
    --data-binary @- \
    "$API/auth/login"
)"

echo "$SALES_LOGIN_RESPONSE" | jq
unset NEW_SALES_PASSWORD
```

신규 사용자 상태를 확인한다.

```bash
NEW_SALES_ME_RESPONSE="$(curl -sS -b "$SALES_COOKIE_JAR" "$API/auth/me")"

echo "$NEW_SALES_ME_RESPONSE" |
jq '{id, team_id, display_name, role_code, region_code, is_admin}'
```

통과 기준:

- `id`가 `NEW_SALES_MEMBER_ID`와 같다.
- `team_id`가 `TEAM_ID`와 같다.
- `role_code`가 `member`다.
- `region_code`가 `busan`이다.
- `is_admin`이 `false`다.

### 5.6 신규 영업사원 소유의 고객사 담당자 등록

일반 영업사원은 자신이 소유한 담당자만 영업 딜 담당자로 사용할 수 있다. 따라서 신규 영업사원으로 로그인한 쿠키를 사용해 담당자를 새로 만든다.

```bash
CONTACT_RESPONSE="$(
  jq -n \
    --arg company_id "$COMPANY_ID" \
    --arg run_tag "$RUN_TAG" \
    '{
      company_id:$company_id,
      name:("API 병원 담당자 " + $run_tag),
      phone:("010" + ($run_tag[-8:])),
      registration_mode:"standard",
      visited:true,
      source_code:"other",
      memo:"신규 영업사원 영업 딜 테스트"
    }' |
  curl -sS \
    -b "$SALES_COOKIE_JAR" \
    -H "Origin: $ORIGIN" \
    -H "Content-Type: application/json" \
    --data-binary @- \
    "$API/customer-contacts"
)"

echo "$CONTACT_RESPONSE" |
jq '{id, company_id, owner_member_id, name, detail}'

CONTACT_ID="$(echo "$CONTACT_RESPONSE" | jq -r '.id // empty')"
echo "CONTACT_ID=$CONTACT_ID"
```

통과 기준:

- `CONTACT_ID`가 비어 있지 않다.
- `company_id`가 `COMPANY_ID`와 같다.
- `owner_member_id`가 `NEW_SALES_MEMBER_ID`와 같다.

### 5.7 테스트 팀장이 제품 등록

제품 생성 API는 같은 팀의 `manager`만 호출할 수 있다. `ADMIN_USER_IDS`에 들어 있는 시스템
관리자라도 팀 역할이 `member`이면 `403 manager_required`가 반환된다. 테스트 팀에 활성 제품이
이미 있고 기존 `PRODUCT_ID`를 그대로 쓸 경우에는 이 절차를 건너뛸 수 있다.

사용자 화면 흐름:

1. 테스트 팀의 팀장 계정으로 로그인한다.
2. `상품 관리` 화면에서 `상품 등록`을 누른다.
3. 제품명에 `$TEST_PRODUCT_NAME` 값을 입력한다.
4. 분류 `시스템`, 제품단가 `12000000`, 유효기간 `24`를 입력한다.
5. 규격에 `TC-06 테스트용`, 비고에 `신규 영업사원 통합 테스트`를 입력한다.
6. `상품 등록`을 눌러 저장한다.
7. 팀장 계정에서 로그아웃하고 신규 영업사원으로 다시 로그인한다.

화면 대신 API로 등록하려면 테스트 팀장 이메일과 비밀번호를 입력하고 다음 명령을 실행한다.
화면에서 이미 등록했다면 이 POST 명령은 실행하지 않는다.

```bash
printf "테스트 팀장 이메일을 입력하고 Enter를 누르세요: "
read -r TEAM_MANAGER_EMAIL
printf "테스트 팀장 비밀번호를 입력하고 Enter를 누르세요: "
read -s TEAM_MANAGER_PASSWORD
printf "\n"

jq -n \
  --arg email "$TEAM_MANAGER_EMAIL" \
  --arg password "$TEAM_MANAGER_PASSWORD" \
  '{email:$email,password:$password}' |
curl -sS \
  -c "$TEAM_MANAGER_COOKIE_JAR" \
  -H "Origin: $ORIGIN" \
  -H "Content-Type: application/json" \
  --data-binary @- \
  "$API/auth/login" |
jq '{id,team_id,display_name,role_code,detail}'

unset TEAM_MANAGER_PASSWORD
```

로그인 응답의 `team_id=TEAM_ID`, `role_code=manager`를 반드시 확인한 뒤 등록한다.

```bash
PRODUCT_CREATE_RESPONSE="$(
  jq -n \
    --arg name "$TEST_PRODUCT_NAME" \
    '{
      name:$name,
      category_code:"system",
      unit_price:12000000,
      shelf_life_months:24,
      spec:"TC-06 테스트용",
      memo:"신규 영업사원 통합 테스트"
    }' |
  curl -sS \
    -b "$TEAM_MANAGER_COOKIE_JAR" \
    -H "Origin: $ORIGIN" \
    -H "Content-Type: application/json" \
    --data-binary @- \
    "$API/products"
)"

echo "$PRODUCT_CREATE_RESPONSE" |
jq '{id,name,category_code,unit_price,shelf_life_months,spec,memo,active,detail}'
```

신규 영업사원 쿠키로 등록 제품이 보이는지 확인하고 ID를 가져온다.

```bash
PRODUCT_RESPONSE="$(
  curl -sS -G \
    -b "$SALES_COOKIE_JAR" \
    --data-urlencode "q=$TEST_PRODUCT_NAME" \
    --data-urlencode "skip=0" \
    --data-urlencode "limit=30" \
    "$API/products"
)"

echo "$PRODUCT_RESPONSE" | jq '{total, items:[.items[]? | {id,name,category_code,unit_price,active}]}'

PRODUCT_ID="$(
  echo "$PRODUCT_RESPONSE" |
  jq -r --arg name "$TEST_PRODUCT_NAME" '.items[]? | select(.name == $name and .active == true) | .id' |
  head -n 1
)"

echo "PRODUCT_ID=$PRODUCT_ID"
```

통과 기준:

- `PRODUCT_ID`가 비어 있지 않다.
- 제품의 `name`이 `TEST_PRODUCT_NAME`과 같다.
- `category_code=system`, `unit_price=12000000`, `active=true`다.

### 5.8 신규 영업사원으로 영업 딜 생성

사용자 화면 흐름:

1. 신규 영업사원이 영업 관리 화면을 연다.
2. `새 영업 건`을 누른다.
3. 테스트 고객사를 선택한다.
4. 자신이 등록한 고객사 담당자를 선택한다.
5. TC-05.5에서 등록하거나 확인한 제품을 선택한다.
6. 첫 영업 단계를 선택한다.
7. 제목을 입력하고 저장한다.

API 입력:

```json
{
  "customer_company_id": "759ac0ae-f2ff-4fcb-a60f-a016803de9d3",
  "customer_contact_id": "신규 영업사원이 생성한 담당자 ID",
  "product_id": "TC-05.5에서 확인한 PRODUCT_ID",
  "sales_pipeline_id": "7a9df25e-f40b-02ff-2452-c2b9a63849ef",
  "sales_pipeline_stage_id": "414ab196-22e9-77f0-6ddc-1ac00cdb9d9e",
  "deal_type_code": "new_installation",
  "deal_amount": 0,
  "opened_on": "실행일",
  "title": "신규 영업사원 API 딜 테스트"
}
```

실행 명령:

```bash
OPENED_ON="$(date +%F)"

DEAL_RESPONSE="$(
  jq -n \
    --arg company_id "$COMPANY_ID" \
    --arg contact_id "$CONTACT_ID" \
    --arg product_id "$PRODUCT_ID" \
    --arg pipeline_id "$PIPELINE_ID" \
    --arg stage_id "$STAGE_ID" \
    --arg deal_type_code "$DEAL_TYPE_CODE" \
    --arg opened_on "$OPENED_ON" \
    --arg run_tag "$RUN_TAG" \
    '{
      customer_company_id:$company_id,
      customer_contact_id:$contact_id,
      product_id:$product_id,
      sales_pipeline_id:$pipeline_id,
      sales_pipeline_stage_id:$stage_id,
      deal_type_code:$deal_type_code,
      deal_amount:0,
      opened_on:$opened_on,
      title:("신규 영업사원 API 딜 테스트 " + $run_tag),
      memo:"신규 계정 발급부터 딜 생성까지 사용자 흐름 테스트"
    }' |
  curl -sS \
    -b "$SALES_COOKIE_JAR" \
    -H "Origin: $ORIGIN" \
    -H "Content-Type: application/json" \
    --data-binary @- \
    "$API/sales-deals"
)"

echo "$DEAL_RESPONSE" |
jq '{
  id,
  title,
  owner_member_id,
  customer_company_id,
  customer_contact_id,
  product_id,
  sales_pipeline_id,
  sales_pipeline_stage_id,
  deal_type_code,
  detail
}'

DEAL_ID="$(echo "$DEAL_RESPONSE" | jq -r '.id // empty')"
echo "DEAL_ID=$DEAL_ID"
```

통과 기준:

- `DEAL_ID`가 비어 있지 않다.
- `owner_member_id`가 `NEW_SALES_MEMBER_ID`와 같다.
- 고객사, 담당자, 제품, 파이프라인, 단계, 영업 유형이 요청값과 같다.
- 응답에 `detail` 오류가 없다.

### 5.9 생성한 영업 딜 상세 조회

```bash
DEAL_DETAIL_RESPONSE="$(
  curl -sS \
    -b "$SALES_COOKIE_JAR" \
    "$API/sales-deals/$DEAL_ID"
)"

echo "$DEAL_DETAIL_RESPONSE" |
jq '{
  id,
  title,
  owner_member_id,
  owner_display_name,
  customer_company_id,
  customer_contact_id,
  product_id,
  sales_pipeline_id,
  sales_pipeline_stage_id,
  deal_type_code,
  opened_on
}'
```

통과 기준은 조회 결과가 5.8의 생성 응답과 같은 것이다.

### 5.10 신규 영업사원 딜 목록에서 확인

```bash
curl -sS \
  -b "$SALES_COOKIE_JAR" \
  "$API/sales-deals?customer_company_id=$COMPANY_ID&skip=0&limit=30" |
jq --arg deal_id "$DEAL_ID" \
  '.items[] | select(.id == $deal_id) | {
    id,
    title,
    owner_member_id,
    customer_company_id,
    customer_contact_id,
    product_id
  }'
```

생성한 딜 한 건이 출력되면 목록 조회까지 통과한 것이다.

### 5.11 영업 딜에 연결된 첫 일정 등록

먼저 테스트 팀에서 사용할 수 있는 일정 분류 코드를 확인한다.

```bash
ACTIVITY_CATEGORIES_RESPONSE="$(
  curl -sS -b "$SALES_COOKIE_JAR" "$API/activity-categories"
)"

echo "$ACTIVITY_CATEGORIES_RESPONSE" | jq '.[] | {code,name,tone}'

ACTIVITY_CATEGORY_CODE="$(
  echo "$ACTIVITY_CATEGORIES_RESPONSE" |
  jq -r 'map(select(.code == "meeting"))[0].code // .[0].code // empty'
)"

echo "ACTIVITY_CATEGORY_CODE=$ACTIVITY_CATEGORY_CODE"
```

`ACTIVITY_CATEGORY_CODE`가 비어 있으면 일정 등록을 진행하지 말고 팀의 일정 분류 설정을
먼저 확인한다. 다음 날짜 계산은 macOS 기본 `date` 명령 기준이다.

```bash
INITIAL_ACTIVITY_DATE="$(date -v+1d +%F)"
INITIAL_ACTIVITY_TITLE="TC-09 첫 미팅 ${RUN_TAG}"

INITIAL_ACTIVITY_RESPONSE="$(
  jq -n \
    --arg company_id "$COMPANY_ID" \
    --arg contact_id "$CONTACT_ID" \
    --arg product_id "$PRODUCT_ID" \
    --arg deal_id "$DEAL_ID" \
    --arg category_code "$ACTIVITY_CATEGORY_CODE" \
    --arg title "$INITIAL_ACTIVITY_TITLE" \
    --arg starts_at "${INITIAL_ACTIVITY_DATE}T10:00:00+09:00" \
    --arg ends_at "${INITIAL_ACTIVITY_DATE}T11:00:00+09:00" \
    '{
      customer_company_id:$company_id,
      customer_contact_id:$contact_id,
      product_id:$product_id,
      sales_deal_id:$deal_id,
      category_code:$category_code,
      title:$title,
      starts_at:$starts_at,
      ends_at:$ends_at,
      all_day:false,
      location:"테스트 고객사 회의실",
      note:"TC-10 미팅 보고서 작성의 기준 일정"
    }' |
  curl -sS \
    -b "$SALES_COOKIE_JAR" \
    -H "Origin: $ORIGIN" \
    -H "Content-Type: application/json" \
    --data-binary @- \
    "$API/activities"
)"

echo "$INITIAL_ACTIVITY_RESPONSE" |
jq '{id,owner_member_id,customer_company_id,customer_contact_id,product_id,sales_deal_id,title,starts_at,briefing_queue_warning,detail}'

ACTIVITY_ID="$(echo "$INITIAL_ACTIVITY_RESPONSE" | jq -r '.id // empty')"
echo "ACTIVITY_ID=$ACTIVITY_ID"
```

통과 기준:

- `ACTIVITY_ID`가 비어 있지 않다.
- `owner_member_id=NEW_SALES_MEMBER_ID`, `sales_deal_id=DEAL_ID`다.
- 고객사·담당자·제품 ID가 앞 단계의 값과 같다.
- `briefing_queue_warning`과 `detail`이 비어 있다.

### 5.12 일정의 미팅 보고서 작성·확정

보고서 초안 요청과 확정 데이터에는 긴 원문과 생성 결과가 포함되므로 이 단계는 화면에서
수행한다.

1. 신규 영업사원으로 `미팅 관리` 또는 TC-09 일정 상세를 연다.
2. `보고서 작성`을 누르고 기준 일정으로 `$INITIAL_ACTIVITY_TITLE`을 선택한다.
3. 미팅 원문에 고객 요구사항, 예산, 도입 희망일, 다음 미팅 필요성이 드러나는 테스트 내용을 입력한다.
4. TC-06에서 만든 영업 딜을 연결한다.
5. `AI 보고서 생성`을 누르고 생성 완료까지 기다린다.
6. 초안을 검토한 후 `확정` 또는 `제출`을 누른다.

확정 후 API에서 보고서를 확인한다.

```bash
REPORTS_RESPONSE="$(
  curl -sS -G \
    -b "$SALES_COOKIE_JAR" \
    --data-urlencode "report_kind=meeting" \
    --data-urlencode "source_activity_id=$ACTIVITY_ID" \
    --data-urlencode "limit=1" \
    "$API/reports"
)"

echo "$REPORTS_RESPONSE" |
jq '{total,items:[.items[]? | {id,report_kind,status_code,author_member_id,source_activity_id,created_at}]}'

REPORT_ID="$(echo "$REPORTS_RESPONSE" | jq -r '.items[0].id // empty')"
echo "REPORT_ID=$REPORT_ID"
```

통과 기준은 `REPORT_ID`가 존재하고 최신 항목의 `report_kind=meeting`,
`status_code=submitted`, `author_member_id=NEW_SALES_MEMBER_ID`,
`source_activity_id=ACTIVITY_ID`인 것이다. 생성 또는 확정 중 오류가 나면 추천 일정 단계로
넘어가지 않는다.

### 5.13 AI 추천 일정 카드 한 개 확인

보고서 확정 뒤 계약관리와 일정관리 AgentRun이 백그라운드에서 순서대로 실행된다. 아래
명령은 최대 약 5분 동안 현재 딜의 표시 가능한 추천을 기다린다.

```bash
for attempt in {1..60}; do
  SUGGESTIONS_RESPONSE="$(
    curl -sS -b "$SALES_COOKIE_JAR" "$API/contract-next-meeting-suggestions"
  )"
  SUGGESTION_COUNT="$(
    echo "$SUGGESTIONS_RESPONSE" |
    jq --arg deal_id "$DEAL_ID" '[.[] | select(.sales_deal_id == $deal_id)] | length'
  )"
  [ "$SUGGESTION_COUNT" -ge 1 ] && break
  sleep 5
done

echo "$SUGGESTIONS_RESPONSE" |
jq --arg deal_id "$DEAL_ID" \
  '[.[] | select(.sales_deal_id == $deal_id) | {
    id,sales_deal_id,customer_company_name,customer_contact_name,reason,
    schedule_management_run_id,schedule_candidates,status_code
  }]'

echo "SUGGESTION_COUNT=$SUGGESTION_COUNT"
```

`SUGGESTION_COUNT=1`이어야 한다. `0`이면 아직 실행 중인지 AgentRun 상태와 백엔드 로그를
확인한다. `2` 이상이면 같은 딜의 pending 추천 중복으로 실패 처리한다.

추천 등록 검증에 쓸 첫 번째 후보를 저장한다. `priority` 숫자가 가장 작은 후보가 화면의
기본 선택값이다.

```bash
SUGGESTION="$(
  echo "$SUGGESTIONS_RESPONSE" |
  jq -c --arg deal_id "$DEAL_ID" '[.[] | select(.sales_deal_id == $deal_id)][0]'
)"

SCHEDULE_RUN_ID="$(echo "$SUGGESTION" | jq -r '.schedule_management_run_id // empty')"
CANDIDATE="$(echo "$SUGGESTION" | jq -c '.schedule_candidates | sort_by(.priority) | .[0]')"
CANDIDATE_TITLE="$(echo "$CANDIDATE" | jq -r '.title // empty')"
CANDIDATE_STARTS_AT="$(echo "$CANDIDATE" | jq -r '.starts_at // empty')"
CANDIDATE_ENDS_AT="$(echo "$CANDIDATE" | jq -r '.ends_at // empty')"

echo "$CANDIDATE" | jq
```

캘린더 화면을 새로 열거나 새로고침했을 때 `AI 추천 일정` 영역에 현재 딜의 카드가 한 개
보이고, 고객사·담당자·추천 사유와 후보 시간이 위 API 결과와 같아야 한다.

### 5.14 캘린더에서 추천 일정 등록

1. TC-11 추천 카드에서 우선순위가 가장 높은 후보를 선택한다.
2. `추천일에 넣기`를 누른다.
3. 성공 알림과 함께 추천 카드가 사라지고 캘린더에 일정이 표시되는지 확인한다.
4. 브라우저 개발자 도구의 Network에서 `POST /api/activities`가 `201`이고 요청의
   `schedule_management_run_id`가 `$SCHEDULE_RUN_ID`인지 확인한다.

화면 등록 후 후보 시간으로 생성된 일정 ID를 가져온다.

```bash
RECOMMENDED_DATE="${CANDIDATE_STARTS_AT%%T*}"

RECOMMENDED_ACTIVITIES_RESPONSE="$(
  curl -sS -G \
    -b "$SALES_COOKIE_JAR" \
    --data-urlencode "start_date=$RECOMMENDED_DATE" \
    --data-urlencode "end_date=$RECOMMENDED_DATE" \
    --data-urlencode "skip=0" \
    --data-urlencode "limit=30" \
    "$API/activities"
)"

RECOMMENDED_ACTIVITY_ID="$(
  echo "$RECOMMENDED_ACTIVITIES_RESPONSE" |
  jq -r \
    --arg deal_id "$DEAL_ID" \
    --arg title "$CANDIDATE_TITLE" \
    '.items[]? | select(.sales_deal_id == $deal_id and .title == $title) | .id' |
  head -n 1
)"

echo "RECOMMENDED_ACTIVITY_ID=$RECOMMENDED_ACTIVITY_ID"
curl -sS -b "$SALES_COOKIE_JAR" "$API/activities/$RECOMMENDED_ACTIVITY_ID" |
jq '{id,sales_deal_id,title,starts_at,ends_at,schedule_conflict_warning,briefing_queue_warning}'
```

통과 기준:

- `RECOMMENDED_ACTIVITY_ID`가 비어 있지 않고 시간과 딜이 후보와 같다.
- 다시 `GET /contract-next-meeting-suggestions`를 호출하면 현재 딜의 pending 카드가 없다.
- 충돌이 없도록 선택했다면 `schedule_conflict_warning`도 비어 있다.

### 5.15 캘린더에서 일정 수동 등록

추천 일정과 겹치지 않는 다음 날을 사용한다.

```bash
MANUAL_ACTIVITY_DATE="$(date -v+2d +%F)"
MANUAL_ACTIVITY_TITLE="TC-13 수동 일정 ${RUN_TAG}"
```

1. 캘린더의 빈 날짜 또는 `일정 추가`를 누른다.
2. 날짜는 `$MANUAL_ACTIVITY_DATE`, 시간은 `14:00~15:00`으로 입력한다.
3. 제목은 `$MANUAL_ACTIVITY_TITLE`을 그대로 입력한다.
4. 고객사, TC-05 담당자, TC-06 제품과 영업 딜을 선택한다.
5. TC-09와 같은 일정 분류를 선택하고 저장한다.
6. Network의 `POST /api/activities`가 `201`이고 요청의
   `schedule_management_run_id`가 `null`이거나 필드가 없는지 확인한다.

화면 등록 후 API로 결과를 찾는다.

```bash
MANUAL_ACTIVITIES_RESPONSE="$(
  curl -sS -G \
    -b "$SALES_COOKIE_JAR" \
    --data-urlencode "start_date=$MANUAL_ACTIVITY_DATE" \
    --data-urlencode "end_date=$MANUAL_ACTIVITY_DATE" \
    --data-urlencode "skip=0" \
    --data-urlencode "limit=30" \
    "$API/activities"
)"

MANUAL_ACTIVITY_ID="$(
  echo "$MANUAL_ACTIVITIES_RESPONSE" |
  jq -r \
    --arg title "$MANUAL_ACTIVITY_TITLE" \
    --arg deal_id "$DEAL_ID" \
    '.items[]? | select(.title == $title and .sales_deal_id == $deal_id) | .id' |
  head -n 1
)"

echo "MANUAL_ACTIVITY_ID=$MANUAL_ACTIVITY_ID"
curl -sS -b "$SALES_COOKIE_JAR" "$API/activities/$MANUAL_ACTIVITY_ID" |
jq '{id,owner_member_id,customer_company_id,customer_contact_id,product_id,sales_deal_id,title,starts_at,ends_at,briefing_queue_warning}'
```

`MANUAL_ACTIVITY_ID`가 존재하고 입력한 연결 정보와 시간이 모두 같아야 한다. 현재 구현은
AI 추천 수락 일정뿐 아니라 캘린더에서 직접 만든 일정에도 브리핑을 자동으로 큐에 넣는다.

### 5.16 등록 일정 클릭 후 AI 브리핑 확인

브리핑도 백그라운드 LLM 실행이므로 두 일정의 상세 응답이 채워질 때까지 기다린다.

```bash
for ACTIVITY_TO_CHECK in "$RECOMMENDED_ACTIVITY_ID" "$MANUAL_ACTIVITY_ID"; do
  ACTIVITY_DETAIL=""
  for attempt in {1..60}; do
    ACTIVITY_DETAIL="$(
      curl -sS -b "$SALES_COOKIE_JAR" "$API/activities/$ACTIVITY_TO_CHECK"
    )"
    [ "$(echo "$ACTIVITY_DETAIL" | jq -r '.ai_briefing != null')" = "true" ] && break
    sleep 5
  done

  echo "$ACTIVITY_DETAIL" |
  jq '{id,title,ai_briefing,briefing_queue_warning,detail}'
done
```

통과 기준:

- `RECOMMENDED_ACTIVITY_ID`와 `MANUAL_ACTIVITY_ID`가 서로 다르다.
- 두 상세 응답 모두 `ai_briefing`이 `null`이 아니다.
- `ai_briefing.highlights`의 각 항목에 제목, 본문, 추천 행동과 근거가 표시되며
  `missing_information`도 화면의 부족 정보와 일치한다.
- 캘린더에서 두 일정을 각각 클릭했을 때 API와 같은 `AI 브리핑`이 보인다.
- `briefing_queue_warning`과 `detail`이 비어 있다.

## 6. 전체 통과 기준

- 관리자가 신규 계정을 발급하면 신규 구성원 ID가 생성된다.
- 신규 계정이 기존 팀의 `member`와 부산 담당지역으로 등록된다.
- 신규 계정으로 로그인할 수 있다.
- 신규 영업사원이 만든 고객사 담당자의 소유자가 신규 영업사원이다.
- 테스트 팀장이 등록한 활성 제품이 신규 영업사원의 제품 선택 목록에 표시된다.
- 신규 영업사원이 영업 딜을 생성할 수 있다.
- 영업 딜의 소유자가 신규 영업사원이다.
- 생성한 딜을 상세와 목록 API에서 다시 조회할 수 있다.
- 일반 영업사원의 관리자 API 호출은 `403`으로 차단된다.
- 중복 이메일 발급은 `409`로 차단된다.
- 다른 고객사 담당자를 선택한 딜 생성은 `422`로 차단된다.
- 딜에 연결된 일정을 만들고 해당 일정의 미팅 보고서를 확정할 수 있다.
- 현재 딜의 pending 추천 일정 카드는 정확히 한 개만 표시된다.
- 추천 후보를 등록하면 카드가 사라지고 후보 시간에 일정이 생성된다.
- 캘린더에서 같은 딜의 일정을 직접 등록할 수 있다.
- 추천 등록 일정과 수동 등록 일정 모두 상세 화면에서 AI 브리핑을 확인할 수 있다.

## 7. 실패 판정표

| 응답 | 의미 | 조치 |
|---|---|---|
| `403 admin_only` | 로그인 사용자가 계정 발급 관리자 아님 | `ADMIN_USER_IDS`와 백엔드 재시작 확인 |
| `403 manager_required` | 제품 등록 사용자의 팀 역할이 팀장 아님 | 대상 팀의 활성 `manager` 계정으로 제품 등록 |
| `422 instant_local_only` | 로컬이 아닌 환경에서 바로 만들기 시도 | `APP_ENV=local` 확인 또는 초대 방식 사용 |
| `409 email_already_exists` | 동일 이메일 계정 존재 | 새 `RUN_TAG`로 다시 시작 |
| `401 invalid_credentials` | 로그인 이메일 또는 비밀번호 불일치 | 입력값 확인 |
| `401 not_authenticated` | 쿠키가 없거나 로그인 실패 | 해당 사용자의 로그인 단계부터 재실행 |
| `422 contact_company_mismatch` | 고객사와 담당자 소속 불일치 | 신규 사용자 쿠키로 같은 고객사의 담당자 생성 |
| `422 contact_owner_mismatch` | 담당자가 다른 영업사원 소유 | 신규 사용자 자신이 만든 담당자 사용 |
| `422 sales_pipeline_stage_pipeline_mismatch` | 단계가 다른 파이프라인 소속 | 문서의 고정 파이프라인·단계 ID 사용 |
| `422 activity_category_code_not_found` | 선택한 일정 분류가 팀에 없음 | `GET /activity-categories` 결과의 활성 코드 사용 |
| 추천 카드 `0개` | 백그라운드 실행 중이거나 보고서 확정·LLM 실행 실패 | 최대 5분 대기 후 AgentRun과 백엔드 로그 확인 |
| 추천 카드 `2개 이상` | 같은 딜의 pending 추천이 중복 저장됨 | 실패로 기록하고 중복 생성 경로 확인 |
| `briefing_queue_warning` 존재 | 일정은 저장됐지만 브리핑 큐 등록 실패 | 경고 내용과 AgentRun 생성 로그 확인 |
| `ai_briefing=null` 지속 | 브리핑 실행 중 또는 실패 | `contract_management_briefing` AgentRun과 LLM 설정 확인 |

## 8. 반복 실행 및 정리

- `RUN_TAG`가 이메일과 데이터 제목을 매번 다르게 만들어 중복을 방지한다.
- 계정 삭제 API는 현재 제공되지 않으므로 발급된 Supabase 사용자와 `member` 행은 자동 삭제할 수 없다.
- 테스트 제품은 팀장 계정의 상품 관리 화면에서 비활성화하거나 삭제한다.
- 테스트 일정·보고서를 먼저 정리한 뒤, 영업 딜은 신규 영업사원 로그인 상태에서 화면 또는 `DELETE /api/sales-deals/{id}`로 삭제할 수 있다.
- 계정이 계속 누적되지 않게 필요한 횟수만 실행한다.
- 테스트가 끝나면 임시 쿠키 파일과 셸 변수를 제거한다.

```bash
rm "$ADMIN_COOKIE_JAR" "$TEAM_MANAGER_COOKIE_JAR" "$SALES_COOKIE_JAR"

unset API ORIGIN ADMIN_EMAIL TEAM_ID COMPANY_ID PRODUCT_ID PIPELINE_ID STAGE_ID
unset DEAL_TYPE_CODE RUN_TAG NEW_SALES_EMAIL NEW_SALES_NAME TEST_PRODUCT_NAME
unset ADMIN_COOKIE_JAR TEAM_MANAGER_COOKIE_JAR SALES_COOKIE_JAR TEAM_MANAGER_EMAIL
unset PRODUCT_CREATE_RESPONSE PRODUCT_RESPONSE
unset ADMIN_LOGIN_RESPONSE ADMIN_ME_RESPONSE ACCOUNT_RESPONSE NEW_SALES_MEMBER_ID
unset SALES_LOGIN_RESPONSE NEW_SALES_ME_RESPONSE CONTACT_RESPONSE CONTACT_ID
unset OPENED_ON DEAL_RESPONSE DEAL_ID DEAL_DETAIL_RESPONSE
unset ACTIVITY_CATEGORIES_RESPONSE ACTIVITY_CATEGORY_CODE INITIAL_ACTIVITY_DATE
unset INITIAL_ACTIVITY_TITLE INITIAL_ACTIVITY_RESPONSE ACTIVITY_ID REPORTS_RESPONSE REPORT_ID
unset SUGGESTIONS_RESPONSE SUGGESTION_COUNT SUGGESTION SCHEDULE_RUN_ID CANDIDATE
unset CANDIDATE_TITLE CANDIDATE_STARTS_AT CANDIDATE_ENDS_AT RECOMMENDED_DATE
unset RECOMMENDED_ACTIVITIES_RESPONSE RECOMMENDED_ACTIVITY_ID MANUAL_ACTIVITY_DATE
unset MANUAL_ACTIVITY_TITLE MANUAL_ACTIVITIES_RESPONSE MANUAL_ACTIVITY_ID ACTIVITY_DETAIL
```

로컬에서 기존 테스트 계정을 임시 관리자로 추가했다면 테스트 후 `backend/.env`의 `ADMIN_USER_IDS`를 원래 값으로 되돌리고 백엔드를 재시작한다.
