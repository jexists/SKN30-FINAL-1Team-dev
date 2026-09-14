# 신규 영업사원 계정·영업 딜 API 테스트 케이스

## 1. 테스트 목표

실제 사용자 흐름에 맞춰 다음 과정을 검증한다.

1. 관리자가 기존 팀에 신규 영업사원 계정을 발급한다.
2. 신규 영업사원이 자신의 계정으로 로그인한다.
3. 신규 영업사원이 고객사 담당자를 등록한다.
4. 신규 영업사원이 제품과 영업 단계를 선택해 영업 딜을 생성한다.
5. 생성한 딜이 신규 영업사원 소유로 조회되는지 확인한다.

이 테스트는 로컬 백엔드를 통해 실제 Supabase Auth와 원격 DB를 변경한다. 신규 계정, 고객사 담당자, 영업 딜은 자동 롤백되지 않는다.

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

ADMIN_COOKIE_JAR="$(mktemp -t salesluv-admin-cookies)"
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

### 5.7 신규 영업사원으로 영업 딜 생성

사용자 화면 흐름:

1. 신규 영업사원이 영업 관리 화면을 연다.
2. `새 영업 건`을 누른다.
3. 테스트 고객사를 선택한다.
4. 자신이 등록한 고객사 담당자를 선택한다.
5. LP100 제품을 선택한다.
6. 첫 영업 단계를 선택한다.
7. 제목을 입력하고 저장한다.

API 입력:

```json
{
  "customer_company_id": "759ac0ae-f2ff-4fcb-a60f-a016803de9d3",
  "customer_contact_id": "신규 영업사원이 생성한 담당자 ID",
  "product_id": "6c39be91-2c1e-5c67-bdd3-0a57fb431859",
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

### 5.8 생성한 영업 딜 상세 조회

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

통과 기준은 조회 결과가 5.7의 생성 응답과 같은 것이다.

### 5.9 신규 영업사원 딜 목록에서 확인

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

## 6. 전체 통과 기준

- 관리자가 신규 계정을 발급하면 신규 구성원 ID가 생성된다.
- 신규 계정이 기존 팀의 `member`와 부산 담당지역으로 등록된다.
- 신규 계정으로 로그인할 수 있다.
- 신규 영업사원이 만든 고객사 담당자의 소유자가 신규 영업사원이다.
- 신규 영업사원이 영업 딜을 생성할 수 있다.
- 영업 딜의 소유자가 신규 영업사원이다.
- 생성한 딜을 상세와 목록 API에서 다시 조회할 수 있다.
- 일반 영업사원의 관리자 API 호출은 `403`으로 차단된다.
- 중복 이메일 발급은 `409`로 차단된다.
- 다른 고객사 담당자를 선택한 딜 생성은 `422`로 차단된다.

## 7. 실패 판정표

| 응답 | 의미 | 조치 |
|---|---|---|
| `403 admin_only` | 로그인 사용자가 계정 발급 관리자 아님 | `ADMIN_USER_IDS`와 백엔드 재시작 확인 |
| `422 instant_local_only` | 로컬이 아닌 환경에서 바로 만들기 시도 | `APP_ENV=local` 확인 또는 초대 방식 사용 |
| `409 email_already_exists` | 동일 이메일 계정 존재 | 새 `RUN_TAG`로 다시 시작 |
| `401 invalid_credentials` | 로그인 이메일 또는 비밀번호 불일치 | 입력값 확인 |
| `401 not_authenticated` | 쿠키가 없거나 로그인 실패 | 해당 사용자의 로그인 단계부터 재실행 |
| `422 contact_company_mismatch` | 고객사와 담당자 소속 불일치 | 신규 사용자 쿠키로 같은 고객사의 담당자 생성 |
| `422 contact_owner_mismatch` | 담당자가 다른 영업사원 소유 | 신규 사용자 자신이 만든 담당자 사용 |
| `422 sales_pipeline_stage_pipeline_mismatch` | 단계가 다른 파이프라인 소속 | 문서의 고정 파이프라인·단계 ID 사용 |

## 8. 반복 실행 및 정리

- `RUN_TAG`가 이메일과 데이터 제목을 매번 다르게 만들어 중복을 방지한다.
- 계정 삭제 API는 현재 제공되지 않으므로 발급된 Supabase 사용자와 `member` 행은 자동 삭제할 수 없다.
- 테스트 영업 딜은 신규 영업사원 로그인 상태에서 화면 또는 `DELETE /api/sales-deals/{id}`로 삭제할 수 있다.
- 계정이 계속 누적되지 않게 필요한 횟수만 실행한다.
- 테스트가 끝나면 임시 쿠키 파일과 셸 변수를 제거한다.

```bash
rm "$ADMIN_COOKIE_JAR" "$SALES_COOKIE_JAR"

unset API ORIGIN ADMIN_EMAIL TEAM_ID COMPANY_ID PRODUCT_ID PIPELINE_ID STAGE_ID
unset DEAL_TYPE_CODE RUN_TAG NEW_SALES_EMAIL NEW_SALES_NAME ADMIN_COOKIE_JAR SALES_COOKIE_JAR
unset ADMIN_LOGIN_RESPONSE ADMIN_ME_RESPONSE ACCOUNT_RESPONSE NEW_SALES_MEMBER_ID
unset SALES_LOGIN_RESPONSE NEW_SALES_ME_RESPONSE CONTACT_RESPONSE CONTACT_ID
unset OPENED_ON DEAL_RESPONSE DEAL_ID DEAL_DETAIL_RESPONSE
```

로컬에서 기존 테스트 계정을 임시 관리자로 추가했다면 테스트 후 `backend/.env`의 `ADMIN_USER_IDS`를 원래 값으로 되돌리고 백엔드를 재시작한다.
