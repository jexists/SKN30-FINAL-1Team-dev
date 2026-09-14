# 추천 카드 API 통합 테스트 가이드

## 1. 테스트 목적

로컬에서 실행 중인 화면과 백엔드를 사용하되, 실제 Supabase DB와 실제 LLM을 연결한 상태에서 다음 흐름을 확인한다.

1. 테스트 계정 로그인
2. 일정의 고객사와 담당자 소속 일치 여부 확인
3. 같은 고객사 소속 담당자 준비
4. 일정 담당자 수정
5. 영업 건 생성
6. 영업 건과 일정 연결
7. 실제 LLM을 사용하는 미팅 보고서 생성
8. AgentRun 완료 여부 확인

이 테스트는 실제 원격 DB를 변경한다. 생성한 테스트 담당자와 영업 건은 자동 롤백되지 않는다.

## 2. 준비 사항

- 백엔드: `http://127.0.0.1:8000`
- 프론트엔드 Origin: `http://localhost:5173`
- 테스트 계정: `bak3036@gmail.com`
- 필요한 명령: `curl`, `jq`, `uuidgen`
- 명령은 프로젝트 루트 터미널에서 실행한다.

비밀번호는 저장소 문서에 기록하지 않는다. 로그인 단계에서 터미널에 한 번 입력하면 이후 명령이 자동으로 사용한다.

## 3. 이번 테스트의 고정 입력값

| 항목 | 값 |
|---|---|
| 일정 ID | `f8ccbccf-87ea-418f-a208-8bca71e41375` |
| 고객사 ID | `759ac0ae-f2ff-4fcb-a60f-a016803de9d3` |
| 제품 ID | `6c39be91-2c1e-5c67-bdd3-0a57fb431859` |
| 파이프라인 ID | `7a9df25e-f40b-02ff-2452-c2b9a63849ef` |
| 파이프라인 단계 ID | `414ab196-22e9-77f0-6ddc-1ac00cdb9d9e` |
| 영업 유형 코드 | `new_installation` |
| 보고서 기준일 | `2026-09-11` |

담당자 ID, 영업 건 ID, AgentRun ID는 API가 새로 생성하므로 응답에서 자동으로 가져온다. 사용자가 직접 채울 필요가 없다.

## 4. 상황 A — 로그인

### 4.1 공통 변수 설정

아래 블록을 그대로 복사해 실행한다. URL에 Markdown 링크 문법을 넣거나 변수명의 밑줄 앞에 역슬래시를 붙이지 않는다.

```bash
API="http://127.0.0.1:8000/api"
ORIGIN="http://localhost:5173"
EMAIL="bak3036@gmail.com"

ACTIVITY_ID="f8ccbccf-87ea-418f-a208-8bca71e41375"
COMPANY_ID="759ac0ae-f2ff-4fcb-a60f-a016803de9d3"
PRODUCT_ID="6c39be91-2c1e-5c67-bdd3-0a57fb431859"
PIPELINE_ID="7a9df25e-f40b-02ff-2452-c2b9a63849ef"
STAGE_ID="414ab196-22e9-77f0-6ddc-1ac00cdb9d9e"
DEAL_TYPE_CODE="new_installation"
REPORT_DATE="2026-09-11"

COOKIE_JAR="$(mktemp -t salesluv-cookies)"
```

### 4.2 비밀번호 입력

다음 명령을 실행하면 커서가 입력을 기다린다.

```bash
printf "테스트 계정 비밀번호를 입력하고 Enter를 누르세요: "
read -s SALES_PASSWORD
printf "\n"
```

입력 중에는 글자가 화면에 표시되지 않는다. 정상 동작이다.

입력 여부만 확인한다. 비밀번호 자체는 출력하지 않는다.

```bash
echo "입력된 비밀번호 길이: ${#SALES_PASSWORD}"
```

출력이 `0`이면 비밀번호가 입력되지 않은 것이므로 4.2를 다시 실행한다.

### 4.3 로그인 API 호출

입력 JSON:

```json
{
  "email": "bak3036@gmail.com",
  "password": "터미널에서 입력한 비밀번호"
}
```

실행 명령:

```bash
LOGIN_RESPONSE="$(
  jq -n \
    --arg email "$EMAIL" \
    --arg password "$SALES_PASSWORD" \
    '{email:$email,password:$password}' |
  curl -sS \
    -c "$COOKIE_JAR" \
    -H "Origin: $ORIGIN" \
    -H "Content-Type: application/json" \
    --data-binary @- \
    "$API/auth/login"
)"

echo "$LOGIN_RESPONSE" | jq
unset SALES_PASSWORD
```

정상 출력은 로그인한 구성원 정보이며 `detail`이 없어야 한다.

로그인 상태를 다시 확인한다.

```bash
curl -sS -b "$COOKIE_JAR" "$API/auth/me" | jq
```

정상 출력 예시:

```json
{
  "display_name": "테스트 사용자",
  "role_code": "member"
}
```

`invalid_credentials`가 나오면 입력한 이메일 또는 비밀번호가 실제 로그인 정보와 다르다. `not_authenticated`가 나오면 로그인에 실패한 상태이므로 다음 단계로 진행하지 않는다.

## 5. 상황 B — 현재 일정 데이터 확인

### 5.1 일정 조회

```bash
ACTIVITY_RESPONSE="$(curl -sS -b "$COOKIE_JAR" "$API/activities/$ACTIVITY_ID")"

echo "$ACTIVITY_RESPONSE" |
jq '{id, customer_company_id, customer_contact_id, sales_deal_id, product_id, starts_at}'
```

### 5.2 현재 담당자 소속 조회

```bash
CURRENT_CONTACT_ID="$(echo "$ACTIVITY_RESPONSE" | jq -r '.customer_contact_id // empty')"
CURRENT_CONTACT_RESPONSE="$(curl -sS -b "$COOKIE_JAR" "$API/customer-contacts/$CURRENT_CONTACT_ID")"

echo "$CURRENT_CONTACT_RESPONSE" |
jq '{id, company_id, owner_member_id, name}'
```

### 5.3 고객사 일치 여부 출력

```bash
ACTIVITY_COMPANY_ID="$(echo "$ACTIVITY_RESPONSE" | jq -r '.customer_company_id // empty')"
CONTACT_COMPANY_ID="$(echo "$CURRENT_CONTACT_RESPONSE" | jq -r '.company_id // empty')"

jq -n \
  --arg activity_company_id "$ACTIVITY_COMPANY_ID" \
  --arg contact_company_id "$CONTACT_COMPANY_ID" \
  '{
    activity_company_id:$activity_company_id,
    contact_company_id:$contact_company_id,
    same_company:($activity_company_id == $contact_company_id)
  }'
```

현재 오류가 재현되는 데이터라면 다음처럼 나온다.

```json
{
  "same_company": false
}
```

이 상태에서는 영업 건 생성이 `contact_company_mismatch`, 보고서 생성이 `meeting_customer_required`로 거절될 수 있다.

## 6. 상황 C — 같은 고객사 소속 테스트 담당자 준비

### 6.1 기존 담당자가 있는지 확인

```bash
CONTACT_LIST_RESPONSE="$(
  curl -sS \
    -b "$COOKIE_JAR" \
    "$API/customer-contacts?company_id=$COMPANY_ID&skip=0&limit=30"
)"

echo "$CONTACT_LIST_RESPONSE" |
jq '.items[]? | {id, name, company_id, owner_member_id}'

CONTACT_ID="$(echo "$CONTACT_LIST_RESPONSE" | jq -r '.items[0].id // empty')"
```

### 6.2 담당자가 없을 때만 생성

현재 데이터 기준으로는 테스트 계정이 사용할 수 있는 해당 고객사 담당자가 없으므로 아래 조건문이 새 담당자를 생성한다. 이미 담당자가 있으면 기존 담당자를 재사용한다.

입력 JSON:

```json
{
  "company_id": "759ac0ae-f2ff-4fcb-a60f-a016803de9d3",
  "name": "API 테스트 담당자",
  "phone": "010-0000-3036",
  "registration_mode": "standard",
  "visited": true,
  "memo": "API 통합 테스트용 담당자"
}
```

실행 명령:

```bash
if [ -z "$CONTACT_ID" ]; then
  CONTACT_CREATE_RESPONSE="$(
    jq -n \
      --arg company_id "$COMPANY_ID" \
      '{
        company_id:$company_id,
        name:"API 테스트 담당자",
        phone:"010-0000-3036",
        registration_mode:"standard",
        visited:true,
        memo:"API 통합 테스트용 담당자"
      }' |
    curl -sS \
      -b "$COOKIE_JAR" \
      -H "Origin: $ORIGIN" \
      -H "Content-Type: application/json" \
      --data-binary @- \
      "$API/customer-contacts"
  )"

  echo "$CONTACT_CREATE_RESPONSE" | jq
  CONTACT_ID="$(echo "$CONTACT_CREATE_RESPONSE" | jq -r '.id // empty')"
fi

echo "CONTACT_ID=$CONTACT_ID"
```

정상 결과에서는 `CONTACT_ID=` 뒤에 UUID가 출력된다. 값이 비어 있으면 다음 단계로 진행하지 않고 API 응답의 `detail`을 확인한다.

## 7. 상황 D — 일정 담당자 수정

입력 JSON은 다음과 같다. `customer_contact_id`에는 앞 단계가 자동으로 구한 값이 들어간다.

```json
{
  "customer_company_id": "759ac0ae-f2ff-4fcb-a60f-a016803de9d3",
  "customer_contact_id": "자동으로 구한 CONTACT_ID"
}
```

실행 명령:

```bash
ACTIVITY_PATCH_RESPONSE="$(
  jq -n \
    --arg company_id "$COMPANY_ID" \
    --arg contact_id "$CONTACT_ID" \
    '{
      customer_company_id:$company_id,
      customer_contact_id:$contact_id
    }' |
  curl -sS \
    -b "$COOKIE_JAR" \
    -H "Origin: $ORIGIN" \
    -H "Content-Type: application/json" \
    -X PATCH \
    --data-binary @- \
    "$API/activities/$ACTIVITY_ID"
)"

echo "$ACTIVITY_PATCH_RESPONSE" |
jq '{id, customer_company_id, customer_contact_id, sales_deal_id}'
```

통과 기준:

- `customer_company_id`가 `759ac0ae-f2ff-4fcb-a60f-a016803de9d3`이다.
- `customer_contact_id`가 출력된 `CONTACT_ID`와 같다.
- 응답에 `detail` 오류가 없다.

## 8. 상황 E — 영업 건 생성

입력 JSON:

```json
{
  "customer_company_id": "759ac0ae-f2ff-4fcb-a60f-a016803de9d3",
  "customer_contact_id": "자동으로 구한 CONTACT_ID",
  "product_id": "6c39be91-2c1e-5c67-bdd3-0a57fb431859",
  "sales_pipeline_id": "7a9df25e-f40b-02ff-2452-c2b9a63849ef",
  "sales_pipeline_stage_id": "414ab196-22e9-77f0-6ddc-1ac00cdb9d9e",
  "deal_type_code": "new_installation",
  "deal_amount": 0,
  "opened_on": "2026-09-11",
  "title": "API 통합 테스트 영업 건",
  "memo": "보고서와 추천 카드 통합 테스트"
}
```

실행 명령:

```bash
DEAL_RESPONSE="$(
  jq -n \
    --arg company_id "$COMPANY_ID" \
    --arg contact_id "$CONTACT_ID" \
    --arg product_id "$PRODUCT_ID" \
    --arg pipeline_id "$PIPELINE_ID" \
    --arg stage_id "$STAGE_ID" \
    --arg deal_type_code "$DEAL_TYPE_CODE" \
    '{
      customer_company_id:$company_id,
      customer_contact_id:$contact_id,
      product_id:$product_id,
      sales_pipeline_id:$pipeline_id,
      sales_pipeline_stage_id:$stage_id,
      deal_type_code:$deal_type_code,
      deal_amount:0,
      opened_on:"2026-09-11",
      title:"API 통합 테스트 영업 건",
      memo:"보고서와 추천 카드 통합 테스트"
    }' |
  curl -sS \
    -b "$COOKIE_JAR" \
    -H "Origin: $ORIGIN" \
    -H "Content-Type: application/json" \
    --data-binary @- \
    "$API/sales-deals"
)"

echo "$DEAL_RESPONSE" |
jq '{id, title, customer_company_id, customer_contact_id, product_id, deal_type_code}'

DEAL_ID="$(echo "$DEAL_RESPONSE" | jq -r '.id // empty')"
echo "DEAL_ID=$DEAL_ID"
```

정상 결과에서는 `DEAL_ID=` 뒤에 UUID가 출력된다. 값이 비어 있으면 다음 단계로 진행하지 않는다.

대표적인 실패 출력:

```json
{
  "detail": "contact_company_mismatch"
}
```

이 오류가 나오면 상황 D의 일정 수정 응답과 `CONTACT_ID`를 다시 확인한다.

## 9. 상황 F — 영업 건을 일정에 실제 연결

보고서 화면의 딜 선택과 별도로, 거래·제품 자료가 브리핑 범위에 포함되게 하려면 일정의 `sales_deal_id`도 저장해야 한다.

입력 JSON:

```json
{
  "sales_deal_id": "자동으로 생성된 DEAL_ID"
}
```

실행 명령:

```bash
ACTIVITY_DEAL_RESPONSE="$(
  jq -n --arg deal_id "$DEAL_ID" '{sales_deal_id:$deal_id}' |
  curl -sS \
    -b "$COOKIE_JAR" \
    -H "Origin: $ORIGIN" \
    -H "Content-Type: application/json" \
    -X PATCH \
    --data-binary @- \
    "$API/activities/$ACTIVITY_ID"
)"

echo "$ACTIVITY_DEAL_RESPONSE" |
jq '{id, customer_company_id, customer_contact_id, sales_deal_id, product_id}'
```

통과 기준은 응답의 `sales_deal_id`와 `DEAL_ID`가 같은 것이다.

## 10. 상황 G — 실제 LLM 미팅 보고서 생성

보고서 생성마다 새로운 멱등성 키를 사용한다.

```bash
IDEMPOTENCY_KEY="$(uuidgen | tr '[:upper:]' '[:lower:]')"
echo "IDEMPOTENCY_KEY=$IDEMPOTENCY_KEY"
```

입력 JSON의 핵심 값:

```json
{
  "report_kind": "meeting",
  "report_date": "2026-09-11",
  "source_activity_id": "f8ccbccf-87ea-418f-a208-8bca71e41375",
  "sales_deal_ids": ["자동으로 생성된 DEAL_ID"],
  "transcript": "LP100 도입 조건과 예산을 논의했습니다. 고객은 제품 자료와 견적서를 요청했습니다. 다음 미팅에서는 납품 일정과 계약 조건을 확인하기로 했습니다."
}
```

실행 명령:

```bash
RUN_RESPONSE="$(
  jq -n \
    --arg idempotency_key "$IDEMPOTENCY_KEY" \
    --arg activity_id "$ACTIVITY_ID" \
    --arg deal_id "$DEAL_ID" \
    '{
      idempotency_key:$idempotency_key,
      report_kind:"meeting",
      report_date:"2026-09-11",
      source_activity_id:$activity_id,
      sales_deal_ids:[$deal_id],
      attachments:[],
      template_snapshot:{
        id:"builtin-meeting-freeform",
        name:"미팅 보고서",
        owner:"",
        updated:"",
        fields:[{
          id:"body",
          label:"보고서 본문",
          type:"textarea",
          required:true,
          aiFilled:true,
          placeholder:"미팅에서 논의한 내용을 입력하세요."
        }]
      },
      content:{
        title:"LP100 도입 상담",
        values:{body:""}
      },
      transcript:"LP100 도입 조건과 예산을 논의했습니다. 고객은 제품 자료와 견적서를 요청했습니다. 다음 미팅에서는 납품 일정과 계약 조건을 확인하기로 했습니다."
    }' |
  curl -sS \
    -b "$COOKIE_JAR" \
    -H "Origin: $ORIGIN" \
    -H "Content-Type: application/json" \
    --data-binary @- \
    "$API/report-generations"
)"

echo "$RUN_RESPONSE" |
jq '{id, agent_code, status_code, current_stage_code, error_code, error_message}'

RUN_ID="$(echo "$RUN_RESPONSE" | jq -r '.id // empty')"
echo "RUN_ID=$RUN_ID"
```

정상 접수 예시:

```json
{
  "agent_code": "meeting_processing",
  "status_code": "queued",
  "error_code": null,
  "error_message": null
}
```

`RUN_ID`가 비어 있고 `422` 상세 내용이 나오면 LLM 호출 전 입력 검증에서 거절된 것이다.

## 11. 상황 H — AgentRun 완료 확인

아래 명령은 최대 약 2분 동안 2초 간격으로 실행 상태를 확인한다.

```bash
for i in {1..60}; do
  RUN_JSON="$(curl -sS -b "$COOKIE_JAR" "$API/agent-runs/$RUN_ID")"

  echo "$RUN_JSON" |
  jq '{status_code, current_stage_code, error_code, error_message}'

  STATUS="$(echo "$RUN_JSON" | jq -r '.status_code // empty')"

  case "$STATUS" in
    completed|partial|failed|cancelled)
      echo "$RUN_JSON" | jq '.output_snapshot'
      break
      ;;
  esac

  sleep 2
done
```

성공 기준:

```json
{
  "status_code": "completed",
  "error_code": null,
  "error_message": null
}
```

완료 결과 전체를 다시 확인하려면 다음을 실행한다.

```bash
curl -sS -b "$COOKIE_JAR" "$API/agent-runs/$RUN_ID" |
jq '{
  id,
  agent_code,
  status_code,
  error_code,
  error_message,
  output_snapshot,
  evidence
}'
```

## 12. 상황별 오류 해석

### `invalid_credentials`

```json
{
  "detail": "invalid_credentials"
}
```

- 이메일 또는 비밀번호가 실제 계정 정보와 다르다.
- 변수명의 `_` 앞에 역슬래시를 붙이지 않았는지 확인한다.
- 로그인 API가 성공하기 전에는 이후 API를 실행하지 않는다.

### `not_authenticated`

```json
{
  "detail": "not_authenticated"
}
```

- 로그인 쿠키가 없거나 만료됐다.
- 상황 A를 다시 실행한다.
- 모든 요청에서 `-b "$COOKIE_JAR"`가 빠지지 않았는지 확인한다.

### `origin_not_allowed`

```json
{
  "detail": "origin_not_allowed"
}
```

- 쓰기 요청의 Origin이 허용된 값과 다르다.
- `ORIGIN="http://localhost:5173"`인지 확인한다.

### `contact_company_mismatch`

```json
{
  "detail": "contact_company_mismatch"
}
```

- 영업 건의 고객사와 담당자의 실제 소속 고객사가 다르다.
- 상황 C와 D를 다시 실행한다.

### `meeting_customer_required`

```json
{
  "detail": "meeting_customer_required"
}
```

- 일정의 고객사와 담당자 소속이 다르거나 담당자가 없다.
- 상황 D의 수정 결과를 확인한다.

### `transcript_required`

- 미팅 보고서 생성 요청의 `transcript`가 비어 있다.
- 상황 G의 입력문을 그대로 사용한다.

### AgentRun `failed`

- 이 경우는 요청이 접수된 뒤 실제 처리 중 실패한 것이다.
- `error_code`, `error_message`, `current_stage_code`를 확인한다.

```bash
curl -sS -b "$COOKIE_JAR" "$API/agent-runs/$RUN_ID" |
jq '{status_code, current_stage_code, error_code, error_message}'
```

## 13. 반복 테스트 시 주의사항

- 같은 보고서 요청을 새 실행으로 테스트하려면 새로운 `IDEMPOTENCY_KEY`를 생성한다.
- 담당자는 두 번째 실행부터 기존 담당자를 재사용한다.
- 영업 건은 실행할 때마다 새로 생성되므로 테스트 데이터가 누적된다.
- 보고서 생성 기록과 추천 결과는 자동 롤백되지 않는다.
- 테스트 중 만든 영업 건이 필요 없으면 화면에서 삭제한다.
- 과거 일정의 고객사·담당자를 무작정 원래 값으로 되돌리면 동일한 422 오류가 다시 발생한다.

## 14. 테스트 종료

로컬에 저장된 로그인 쿠키 파일과 셸 변수를 제거한다.

```bash
rm "$COOKIE_JAR"
unset API ORIGIN EMAIL ACTIVITY_ID COMPANY_ID PRODUCT_ID PIPELINE_ID STAGE_ID
unset DEAL_TYPE_CODE REPORT_DATE COOKIE_JAR CONTACT_ID DEAL_ID RUN_ID
unset LOGIN_RESPONSE ACTIVITY_RESPONSE CURRENT_CONTACT_RESPONSE CONTACT_LIST_RESPONSE
unset CONTACT_CREATE_RESPONSE ACTIVITY_PATCH_RESPONSE DEAL_RESPONSE ACTIVITY_DEAL_RESPONSE
unset RUN_RESPONSE RUN_JSON STATUS IDEMPOTENCY_KEY
```

이 정리는 로컬 터미널 변수와 쿠키 파일만 제거한다. 원격 DB에 생성한 담당자, 영업 건, AgentRun은 삭제하지 않는다.
