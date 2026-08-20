# SalesLuv API 공통 규약

이 문서는 ERD 확정 이후 모든 SalesLuv 기능 API에 공통으로 적용할 백엔드 기준이다.

- 데이터 기준: [SalesLuv 최종 ERD](../SalesLuv_ERD.md)
- Agent 동작 기준: [SalesLuv 멀티에이전트 운영 플로우](../multiagent/SalesLuv_멀티에이전트_운영_플로우.html)
- 화면 기준: [SalesLuv 화면 기준](../../../demo/layout_v3.html)
- 프론트 제안 원본: [대시보드 API 요구사항](dashboard-api-spec.md)

이 문서는 경로, 인증, 권한, 직렬화, 페이지네이션, 오류, 파일과 비동기 Agent 규칙을 정한다. 현재 구현된 엔드포인트는 17절과 FastAPI가 생성한 `/openapi.json`을 함께 기준으로 하며 대시보드 고유 요구사항은 마지막 절에 둔다.

## 1. API 계약 관리

- 기본 경로는 `/api`이며 현재는 버전을 붙이지 않는다.
- 외부 소비자나 하위 호환성 유지가 필요해질 때 `/api/v1`을 추가한다.
- 그전의 breaking change는 백엔드 규약, Pydantic 모델, 프론트 사용처를 같은 PR에서 변경한다.
- 배포된 실제 요청·응답 스키마는 FastAPI의 `/docs`와 `/openapi.json`으로 확인한다.
- 수동 OpenAPI YAML을 별도로 관리하지 않는다.
- 구현이 이 문서와 다르면 생성된 OpenAPI가 아니라 구현을 고쳐야 한다. 규약 자체를 바꿀 때는 문서와 구현을 함께 변경한다.

## 2. 경로, 이름과 식별자

- 업무 리소스 URL은 영문 소문자, 복수 명사, `kebab-case`를 사용한다.
- Query와 JSON 필드명은 `snake_case`를 사용한다.
- 업무 리소스 URL은 단수형 DB 테이블명과 독립적으로 복수 명사를 사용한다. 예: `/api/customer-companies`, `/api/support-requests`, `/api/agent-runs`.
- 종속 리소스는 부모 아래에 둔다. 예: `/api/support-requests/{request_id}/responses`.
- 상태 전이는 마지막 경로에 동사를 사용한다. 예: `POST /api/reports/{report_id}/submit`.
- 모든 내부 `id`와 `*_id`는 하이픈을 포함한 소문자 UUID 문자열이다. 신규 ID는 서버가 UUID v4로 생성한다.
- `deal_no`, `order_no`, `document_no` 같은 업무 번호는 표시·검색용 값이며 내부 ID를 대신하지 않는다.
- 생성 요청에서 서버 생성 ID, 업무 번호, `team_id`, 작성자 ID, 생성·수정 시각을 받지 않는다.

```http
GET /api/activities?start_date=2026-08-12
GET /api/orders/9f64618b-8ed8-4aed-9560-78b25228dbe5
```

## 3. 인증과 세션

- 브라우저 인증은 Supabase Auth의 이메일과 비밀번호로 시작한다. 토큰 발급과 검증은 Supabase가
  담당하고, 팀·역할·활성 판단은 `public.member`가 담당한다. Supabase 사용자 id가 곧 `member.id`다.
- 인증 API는 `POST /api/auth/login`, `POST /api/auth/refresh`, `GET /api/auth/me`,
  `POST /api/auth/logout` 네 개만 둔다.
- 쿠키는 세 개다. `salesluv_access`(`HttpOnly`, `Path=/api`),
  `salesluv_refresh`(`HttpOnly`, `Path=/api/auth`), 그리고 프론트가 세션 복원 시도 여부만
  판단하는 `salesluv_signed_in`(`Path=/`, 값은 `1`). 모두 `SameSite=Lax`를 적용한다.
- 운영 HTTPS에서는 `Secure`를 반드시 적용하고 `Domain`을 지정하지 않아 host-only 쿠키로 둔다.
- 세션 토큰과 비밀번호를 JSON 응답이나 브라우저 저장소에 노출하지 않는다.
- 프론트엔드는 API 요청에 credentials를 포함한다. 전역 `Content-Type`은 지정하지 않고 요청 본문에 맞게 클라이언트가 설정하게 한다.
- 세션 만료 시간은 서버 설정으로 관리하며 MVP에는 refresh API를 두지 않는다. 만료 후 다시 로그인한다.
- 상태 변경 요청은 `Origin`이 환경별 CORS 허용 목록과 일치하는지 검사한다.
- 로그인 실패는 계정 존재 여부를 구분하지 않고 `401 invalid_credentials`로 응답하며 반복 실패 요청을 제한한다.
- 로그아웃은 쿠키를 폐기하고 body 없는 `204 No Content`를 반환한다.

## 4. 권한과 팀 범위

- 현재 ERD에서는 `team`이 최상위 데이터 경계다. 조직 범위는 사용하지 않는다.
- 서버는 매 요청에서 세션의 회원이 활성 상태인지, 역할과 현재 팀이 유효한지 확인한다.
- `member.role_code`의 API 값은 `member`, `manager` 두 개만 사용한다.
- `team_id`, 작성자, 요청자와 기본 담당자는 인증 정보로 결정한다. 요청값만으로 소유권을 정하지 않는다.
- 담당자 필드가 있는 업무 리소스에서 팀원은 본인 담당 데이터만 조회·변경한다.
- 팀 공유 기준정보와 공지는 같은 팀 안에서 기능별 역할 규칙을 적용한다.
- 팀장은 같은 팀의 활성 팀원 데이터를 조회하며 기능이 허용한 경우에만 담당자를 배정한다.
- 담당자 범위를 지원하는 조회는 `owner_member_id`를 같은 Query key로 반복한다.

```http
GET /api/activities?owner_member_id=9f64618b-8ed8-4aed-9560-78b25228dbe5&owner_member_id=9d0dd54b-641a-421f-aa21-7d724d22f914
```

- 팀장이 `owner_member_id`를 생략하면 같은 팀의 활성 팀원 전체, 팀원이 생략하면 본인으로 해석한다.
- 팀원이 담당자 범위를 보내거나 팀장이 허용 범위를 넓히려 하면 `403 scope_not_allowed`를 반환한다.
- 다른 팀 ID나 다른 팀 리소스를 직접 지정하면 존재 여부를 숨기기 위해 `404`를 반환한다.
- 목록, 상세, 집계, 내보내기에는 같은 범위 검사를 적용한다. 페이지 응답이나 합계에도 범위 밖 데이터가 섞이면 안 된다.
- 공지처럼 담당자 범위와 무관한 리소스와 개인 수신 데이터는 기능 명세에서 별도로 밝힌다.

## 5. 요청·응답 모델

- 요청과 응답은 Pydantic 모델과 FastAPI의 명시적 `response_model`로 정의한다.
- 생성, 부분 수정, 조회 모델을 분리한다. ORM 객체나 임의의 `dict`를 API 계약으로 사용하지 않는다.
- JSON body 모델에 `ConfigDict(extra="forbid")`를 적용한다.
- 숫자, 불리언, enum처럼 잘못된 자동 변환이 위험한 필드는 strict 타입이나 validator로 검증한다.
- 알 수 없는 JSON 필드와 해당 엔드포인트가 받지 않는 Query는 `422 Unprocessable Entity`로 거절한다.
- 시스템 판단에 쓰는 고정 wire 값은 영문 소문자 `snake_case`로 저장한다.
- 고정 의미는 영업 phase `sales|quote|contract|order|closed`, 영업 결과 `in_progress|confirmed|cancelled`, 일정 성격 `meeting|task`, 발주 결과 `in_progress|completed|cancelled`, 파이프라인 상태 `draft|published|archived`다.
- 고객 상태, 일정 분류, 일정 태그, 딜 유형, 발주 상태와 영업 단계의 사람용 이름은 팀별 설정 행에서 조회한다. 프론트가 코드로 이름을 다시 만들지 않는다.
- nullable 응답 필드는 값을 알 수 없거나 없으면 key를 유지하고 `null`을 반환한다.
- 목록·태그·자식 컬렉션은 값이 없으면 `[]`를 반환하며 `null`로 보내지 않는다.
- 서버가 계산할 수 있는 `D-4`, `3일 전`, 금액 서식, 파일 크기 라벨 같은 표시 문자열은 반환하지 않는다.

## 6. HTTP 메서드와 성공 응답

| 작업 | 메서드 | 성공 상태 | 응답 |
|---|---|---:|---|
| 목록·상세 조회 | `GET` | `200` | 조회 모델 또는 페이지 객체 |
| 리소스 생성 | `POST` | `201` | 생성된 조회 모델과 `Location` header |
| 부분 수정 | `PATCH` | `200` | 수정된 조회 모델 |
| 동기 상태 전이 | `POST` | `200` | 전이 후 조회 모델 |
| 비동기 작업 시작 | `POST` | `202` | 실행 조회 모델과 `Location` header |
| 삭제·로그아웃 | `DELETE` 또는 `POST` | `204` | body 없음 |

- `success`, `data`, `message` 공통 포장은 사용하지 않는다.
- 생성·수정·삭제 성공 안내 문구는 HTTP 상태와 실행한 동작을 기준으로 프론트가 표시한다.
- 부분 성공처럼 서버만 아는 결과는 문장 대신 `created_count`, `skipped_count`, `warning_codes` 같은 구조화된 필드로 반환한다.
- 전체 교체가 필요한 리소스가 확정되기 전까지 `PUT`은 사용하지 않는다.
- 데이터가 없는 목록은 `404`가 아니라 빈 페이지를 반환한다.

## 7. 목록, 검색과 정렬

- 증가하는 목록은 offset 방식의 `skip`, `limit`을 사용한다.
- 공통 기본값은 `skip=0`, `limit=30`이며 `skip >= 0`, `1 <= limit <= 100`이어야 한다.
- 기능 명세는 더 작은 최대 `limit`을 정할 수 있지만 100을 넘길 수 없다.
- 페이지 응답의 필드명은 아래와 같이 고정한다.

```json
{
  "items": [],
  "skip": 0,
  "limit": 30,
  "total": 82,
  "has_more": true,
  "next_skip": 30
}
```

- `total`은 현재 필터 전체 건수다.
- `has_more`는 `skip + items.length < total`로 계산한다.
- `next_skip`은 다음 데이터가 있으면 `skip + items.length`, 없으면 `null`이다.
- 정렬은 기능 명세가 허용한 `sort_by`와 `sort_order=asc|desc`만 받는다.
- 주 정렬값이 같으면 `id`를 보조 정렬값으로 사용해 순서를 고정한다.
- 동일 Query의 복수 값은 쉼표 문자열이 아니라 같은 key를 반복한다.
- 날짜 범위의 `start_date`, `end_date`는 양 끝 날짜를 포함하며 시작일이 종료일보다 늦으면 `422`다.
- 검색·필터·집계·탭 수·내보내기는 페이지가 아니라 같은 전체 필터 결과를 기준으로 한다.
- 항목 수가 고정된 enum·설정 목록만 기능 명세에서 페이지네이션을 생략할 수 있다.

## 8. 날짜, 시간, 금액과 파일 크기

- 업무 기준 시간대는 `Asia/Seoul`이다.
- 날짜는 `YYYY-MM-DD`, 월은 `YYYY-MM` 형식을 사용한다.
- 일시는 `+09:00`을 포함한 ISO 8601 형식을 사용하며 offset 없는 일시는 거절한다.
- DB의 일시는 `timestamptz`로 저장하고 API 경계에서 업무 시간대로 변환한다.
- 한 요청의 집계는 요청 시작 시각에 고정한 `as_of` 하나를 사용한다.
- 시간 의존 집계 응답은 `as_of`를 포함한다.
- 업무상 하루는 `[00:00:00, 다음 날 00:00:00)` 반개방 구간으로 계산한다.
- 금액은 KRW 원 단위 정수로 전달하고 쉼표나 통화 기호를 포함하지 않는다.
- 파일 크기는 정수 `byte_size`로 전달한다.
- 비율과 집계식은 기능 명세가 분자, 분모, 반올림 규칙을 함께 정의한다.

```json
{
  "starts_at": "2026-08-12T14:30:00+09:00",
  "target_month": "2026-08",
  "deal_amount": 1200000,
  "byte_size": 2516582
}
```

## 9. `PATCH`, 검증과 트랜잭션

- `PATCH`에서 필드 생략은 기존 값 유지다.
- nullable 필드의 명시적 `null`은 값 제거다.
- non-nullable 필드의 `null`은 `422`다.
- 빈 문자열은 `null` 대신 사용하지 않는다. 빈 문자열을 허용하지 않는 필드는 `422`다.
- 잘못된 값, 다른 팀의 FK, 이름으로 추측한 FK를 서버가 자동 보정하거나 자동 생성하지 않는다.
- FK를 받는 요청은 대상 존재 여부, 같은 팀 소속, 활성·보관 상태를 함께 검증한다.
- 루트 리소스와 자식, 상태 전이와 이력 기록, 승인과 업무 반영은 각각 한 DB 트랜잭션에서 처리한다.
- 상태 전이는 현재 상태를 조건으로 원자적으로 갱신하고 허용되지 않은 전이는 `409 invalid_state_transition`을 반환한다.
- Agent 실행 시 실제 사용한 원천 필드를 `agent_run.input_snapshot`에 저장하고, 확정 시 같은 필드의 현재 값과 비교한다. 값이 바뀌었으면 `409 stale_agent_result`로 거절한다.

## 10. 에러

- 업무·권한 에러는 FastAPI 기본 `detail` key에 안정적인 영문 `snake_case` 코드를 넣는다.

```json
{
  "detail": "activity_not_found"
}
```

- Pydantic 요청 검증 오류는 FastAPI 기본 `422` 오류 배열을 사용한다.
- 프론트는 `detail` 코드를 사용자 문구로 바꾸며 서버는 내부 예외나 민감값을 응답에 넣지 않는다.

| 상태 | 사용 기준 |
|---:|---|
| `400` | 문법은 맞지만 요청 전체를 해석할 수 없음 |
| `401` | 세션 없음·만료·위조 또는 로그인 실패 |
| `403` | 인증은 유효하지만 역할·범위가 허용되지 않음 |
| `404` | 리소스 없음 또는 다른 팀 리소스 은닉 |
| `409` | 중복, 허용되지 않은 상태 전이, stale 결과, idempotency 충돌 |
| `413` | 업로드 크기 제한 초과 |
| `415` | 지원하지 않거나 실제 내용과 불일치하는 파일 형식 |
| `422` | 필드, Query, 경로 값 검증 실패 |
| `429` | 로그인·Agent 등 요청 제한 초과 |
| `503` | DB나 필수 외부 서비스 일시 장애 |

## 11. 삭제, 비활성화와 상태 전이

- `deleted_at`이 있는 업무 리소스는 hard delete 대신 soft delete하고 일반 조회에서 제외한다.
- 팀원과 상품처럼 `active`가 있는 기준정보는 삭제 대신 비활성화한다.
- 참조 이력을 깨는 삭제는 실행하지 않고 기능에 따라 보관 처리하거나 `409 resource_in_use`를 반환한다.
- 삭제 성공은 `204`, 이미 없거나 접근할 수 없는 대상은 `404`다.
- 제출, 승인, 반려, 완료, 취소처럼 감사 의미가 있는 변경은 일반 `PATCH status_code`가 아니라 명시적 상태 전이 API로 처리한다.
- 허용 상태, 실행 역할, 동반 생성 데이터는 기능 명세가 상태표로 정의한다.
- `draft` 파이프라인과 단계만 수정할 수 있다. 한 번 published된 파이프라인과 단계는 이름·색상·순서를 포함해 모두 불변이며 변경은 새 draft 복사본에서 수행한다.
- archived 파이프라인은 기존 딜 조회에는 포함하지만 신규 딜·단계 이동 선택지에서는 제외한다.
- 딜 단계 이동은 같은 `sales_pipeline_id` 안에서만 허용하고 요청의 `expected_sales_pipeline_stage_id`가 현재 값과 다르면 `409 invalid_state_transition`을 반환한다.

## 12. 중복 요청과 동시 수정

- `GET` 이외 요청은 클라이언트가 자동 재시도하지 않는다.
- 사용자가 비동기 Agent 실행을 시작하는 `POST`는 `Idempotency-Key` header를 필수로 받는다.
- `Idempotency-Key` 값은 클라이언트가 매 동작마다 새로 생성한 UUID v4이며 형식이 다르면 `422`다.
- 서버는 key를 `agent_run.idempotency_key`에 실행 이력과 함께 보존하고 로그인 회원 범위에서 비교한다.
- 같은 key와 같은 요청은 `200`으로 기존 실행 조회 모델을 반환하고, 같은 key의 다른 요청은 `409 idempotency_key_reused`로 거절한다.
- key가 누락되면 `422`다. Agent 내부 호출은 `parent_run_id`로 추적하며 이 header를 사용하지 않는다.
- MVP에는 모든 CRUD에 적용하는 범용 optimistic lock을 두지 않는다. 상태 전이는 DB에서 원자적으로 검증하며, 실제 동시 편집이 필요한 리소스에는 `version` 또는 `expected_updated_at`을 추가한다.

## 13. 파일

- 파일 업로드는 `multipart/form-data`를 사용하며 JSON base64 업로드는 허용하지 않는다.
- 전역 JSON `Content-Type` header를 강제하지 않아 multipart boundary를 클라이언트가 만들게 한다.
- 원본 파일명은 표시용으로만 보관하고 저장 경로에는 서버 생성 `storage_key`를 사용한다.
- 확장자, 선언된 MIME, 실제 파일 signature를 함께 검사한다.
- 허용 형식과 최대 크기는 업로드 기능별로 명시하고 위반 시 `413` 또는 `415`를 반환한다.
- 압축 파일은 내부 파일 수와 압축 해제 크기를 제한한다.
- 사용자 HTML은 인라인 실행하지 않고 다운로드 attachment 또는 안전한 변환 결과로 제공한다.
- `storage_key`와 내부 저장소 주소는 응답하지 않는다. 다운로드도 매번 팀 권한을 검사한다.
- 추출 텍스트와 OCR·STT 결과는 원본 파일과 같은 권한으로 보호한다.
- 문서 버전 번호는 서버가 트랜잭션 안에서 할당한다.
- 파일 처리 공통 상태는 `uploaded`, `processing`, `completed`, `failed`다.

## 14. LLM과 Agent

이 절은 후속 Agent API가 따라야 할 계약이다. 현재 17절의 라우터에는 `/api/agent-runs`가 아직 등록되어 있지 않다.

- Agent 요청에도 프론트 요청과 동일한 입력 검증, 팀 범위와 권한 검사를 적용한다.
- 장시간 작업 시작은 `202 Accepted`, 실행 리소스 `Location`, 권장 polling 간격 `Retry-After`를 반환한다.
- 클라이언트는 `GET /api/agent-runs/{agent_run_id}`로 polling한다.
- Agent 공통 상태는 `queued`, `running`, `completed`, `failed`다.
- `queued`에서는 `started_at=null`, 실행 종료 전에는 `finished_at=null`이다.
- polling 응답에서 작업 자체가 실패했어도 조회는 `200`이고 `status_code=failed`와 안전한 오류 코드를 반환한다.
- `completed`는 제안·초안 생성 완료이며 업무 데이터 반영 완료가 아니다.
- Agent가 제안한 고객, 영업 딜의 견적·계약 정보, 일정, 보고서 변경은 인증된 사용자의 별도 확정 요청 후 반영한다.
- `meeting_analysis.output_snapshot.support_candidates`는 제안이며 사용자 확정 전에는 `support_request`를 만들지 않는다. 확정된 후보만 C/S 요청 생성 API로 저장한다.
- 검증 실패, 사용자 거절 또는 Agent 실패 시 확정 업무 데이터는 변경하지 않되 실패 실행 이력은 `agent_run`에 남긴다.
- 입력·출력·근거에는 비밀번호, 토큰, 불필요한 개인정보와 권한 밖 원문을 복제하지 않는다.
- 업로드 문서와 고객 입력은 명령이 아니라 신뢰하지 않는 데이터로 취급한다.
- Agent 간 호출은 `parent_run_id`로 연결하고 각 실행의 권한과 근거를 독립적으로 기록한다.
- MVP 전송 방식은 polling 하나만 사용한다. 측정상 polling이 부족할 때 SSE나 webhook을 추가한다.

## 15. 최소 보안과 로그

- CORS는 환경별로 허용한 프론트엔드 origin만 정확히 등록하고 credentials를 허용한다.
- 운영 API는 HTTPS만 허용한다.
- 토큰, 세션, 비밀번호, API 키, 고객 원문과 SQL 파라미터를 로그에 남기지 않는다.
- SQL echo는 합성 데이터만 쓰는 로컬 환경 외에는 끈다.
- 외부 LLM·OCR·STT로 원문을 보내기 전에 권한, 허용된 제공자와 최소 전송 범위를 확인한다.
- 다운로드, Agent 실행, 승인 같은 민감 작업은 사용자와 대상 ID를 감사 가능한 형태로 남기되 원문은 남기지 않는다.

## 16. 기능별 명세의 완료 조건

각 기능 API 명세는 구현 전에 다음을 모두 정한다.

- 메서드와 경로, 권한 역할과 담당자 범위
- Path·Query·body 요청 모델과 응답 모델
- enum 값과 상태 전이표
- 기본 정렬, 검색·필터 허용 목록과 페이지 제한
- 생성·수정·삭제·승인 시 트랜잭션 범위
- 발생 가능한 `detail` 코드와 idempotency 적용 여부
- 정상, 검증 실패, 권한 경계, 중복·상태 충돌 검사

개인 알림, 보고 양식 편집, Agent 도구 호출 감사는 리소스와 수명주기가 확정되기 전까지 API를 만들지 않는다. 견적·계약 메타데이터는 별도 리소스가 아니라 `sales_deal`에 포함한다.

## 17. 현재 구현된 API 계약

아래 경로가 현재 FastAPI 라우터에 등록되어 있다. 요청·응답의 nullable, 길이, strict 타입은 각 Pydantic 모델과 생성된 `/openapi.json`이 최종 기준이다.

| 기능 | 메서드와 경로 | 응답·주요 규칙 |
|---|---|---|
| 상태 | `GET /api/health`, `GET /api/health/db` | 앱/DB 상태 |
| 인증 | `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout` | `SessionRead`; logout `204` |
| 고객 상태 선택지 | `GET /api/customer-contact-statuses` | active 팀 설정, `position` 순 |
| 고객사 | `GET/POST /api/customer-companies`, `GET/PATCH /api/customer-companies/{company_id}` | 목록은 `q,skip,limit`; 회사 수정은 manager |
| 고객 담당자 | `GET/POST /api/customer-contacts`, `GET/PATCH /api/customer-contacts/{contact_id}` | 요청은 `status_code`, 응답은 상태 UUID·code·name·tone 포함 |
| 일정 선택지 | `GET /api/activity-categories?activity_type=...`, `GET /api/activity-action-tags?activity_type=...` | `meeting|task` 필수, active 팀 설정만 |
| 일정 | `GET/POST /api/activities`, `GET/PATCH/DELETE /api/activities/{activity_id}` | 목록은 `start_date` 필수, `end_date,owner_member_id,skip,limit`; 응답에 category/tag UUID·code·name·tone |
| 파이프라인 | `GET /api/sales-pipelines`, `GET /api/sales-pipelines/{sales_pipeline_id}/stages` | published와 archived 조회; default 우선, 단계는 `position` 순 |
| 딜 유형 | `GET /api/sales-deal-types` | active 팀 설정만 |
| 상품 | `GET /api/products` | active 상품; `q,skip,limit` |
| 영업 딜 | `GET/POST /api/sales-deals`, `GET/PATCH/DELETE /api/sales-deals/{sales_deal_id}` | 목록은 `q,start_date,end_date,owner_member_id,sales_pipeline_id,sales_pipeline_stage_id,phase_code,skip,limit` |
| 딜 이동 | `POST /api/sales-deals/{sales_deal_id}/move` | `expected_sales_pipeline_stage_id`, 목표 `sales_pipeline_stage_id`, `stage_position` |
| 발주 상태 | `GET /api/purchase-order-statuses` | active 팀 설정과 고정 `outcome_code` |
| 발주 | `GET/POST /api/orders`, `GET/PATCH/DELETE /api/orders/{purchase_order_id}` | 목록은 `q,supplier_name,stage_code,start_date,end_date,owner_member_id,skip,limit`; 생성 시 딜과 1개 이상 품목 필수 |
| 발주 이동 | `POST /api/orders/{purchase_order_id}/move` | `expected_stage_code`, 목표 `stage_code` |
| C/S | `GET/POST /api/support-requests`, `GET /api/support-requests/{request_id}` | 목록은 `q,status_code,skip,limit`; 상태 `in_progress|completed` |
| C/S 전이·답변 | `POST /api/support-requests/{request_id}/transition`, `POST /api/support-requests/{request_id}/responses` | expected 상태 비교; 답변 생성 `201` |
| 일정 완료 | `POST /api/activities/{activity_id}/complete` | 본문 없음; 완료 시각은 서버가 정함 |
| 보고서 | `GET/POST /api/reports`, `GET/PATCH/DELETE /api/reports/{report_id}` | 목록은 `q,report_kind,status_code,start_date,end_date,author_member_id,skip,limit` |
| 보고서 제출 | `POST /api/reports/{report_id}/submit` | `expected_status_code` 비교; `draft`만 제출 가능 |
| 공지·지시 | `GET /api/notices`, `GET /api/notices/{notice_id}` | 목록은 `scope,q,published_from,published_to,skip,limit` |
| 보고서 초안 실행 | `POST /api/agent-runs`, `GET /api/agent-runs/{agent_run_id}` | `202` + `Location` + `Retry-After`; polling 으로 상태 확인 |
| 대시보드 | `GET /api/dashboard` | `date?,owner_member_id*?,notice_limit=3,renewal_within_days?`; 카드 집계와 주간 밴드를 한 번에 반환 |
| 자료실 | `GET/POST /api/documents`, `GET/PATCH /api/documents/{document_id}` | 목록은 `q,category_code,customer_company_id,sales_deal_id,created_by_member_id,skip,limit` |
| 자료 파일 | `POST /api/documents/{document_id}/files`, `GET /api/documents/{document_id}/files/{file_id}/download` | `multipart/form-data` 업로드; 다운로드는 짧은 서명 URL |

### 일정 완료 처리

- 완료 여부는 `completed_at` 하나로 표현한다. 완료면 시각이 있고 아니면 `null`이다.
- 완료 시각은 서버가 정하므로 요청 본문을 받지 않는다.
- 일반 `PATCH /api/activities/{activity_id}`로는 `completed_at`을 바꿀 수 없다. 보내면 `422`다.
- 이미 완료된 일정의 완료 요청은 `409 already_completed`다.
- 유스케이스가 완료만 정의하므로 완료 취소 endpoint 는 두지 않는다.
- 조회 범위와 잠금 규칙은 일정 상세·수정과 같다.

### 보고서의 상태와 작성 범위

- 보고서 종류는 유스케이스의 미팅·일자별·주간에 대응하는 `meeting`, `daily`, `weekly`다.
- 상태는 `draft`, `submitted`, `approved`, `rejected`, `changes_requested`다. 검토 결과 세 가지는 유스케이스 RPT-004의 확인·반려·수정 요청에 대응한다.
- 현재 API가 만드는 값은 `draft`와 `submitted` 둘이다. 검토 상태 전이는 팀장 기능이라 아직 없다.
- 생성은 항상 `draft`로 시작한다. 요청으로 `status_code`나 작성자를 정할 수 없다.
- 수정과 삭제는 `draft`와 `changes_requested`에서만 허용하고 그 밖의 상태는 `409 report_not_editable`이다.
- 제출은 `draft` 또는 `changes_requested`에서 시작한다. 팀장이 수정 요청하면 팀원이 다시 고쳐 제출한다.
- `weekly`는 `period_start`와 `period_end`가 모두 필요하고 `period_end >= period_start`여야 한다.
- `meeting`은 근거가 되는 `source_activity_id`가 필요하다.
- `activity_ids`로 묶는 일정은 같은 팀에서 조회 가능한 일정만 허용하며 아니면 `404 activity_not_found`다.
- 검토(`approved`, `rejected`)와 `reviewed_by_member_id` 설정은 팀장 기능이라 이번 범위에 없다.
### 공지와 개인 지시의 조회 범위

- `notice.recipient_member_id`가 NULL이면 팀 공지, 값이 있으면 그 사람에게 온 개인 지시다.
- 응답의 `scope`가 `team`과 `personal`을 구분해 주므로 프론트가 `recipient_member_id`로 다시 판정하지 않는다.
- 담당자 범위와 무관하다. 팀 공지는 같은 팀 전체가 보고 개인 지시는 수신자 본인만 본다.
- `scope`를 생략하면 팀 공지와 본인 수신 지시를 함께 조회한다.
- 다른 사람에게 온 지시는 팀장에게도 보이지 않는다.
- `image_storage_key`는 내부 저장소 주소라 응답하지 않고 `image_alt`만 내보낸다.
- 각 `scope`의 전체 건수는 페이지 응답의 `total`로 얻는다.

### 보고서 초안 실행

- 현재 사람이 시작할 수 있는 `agent_code`는 `report_writing` 하나다. 멀티에이전트는 아직 없다.
- `LLM_API_URL`, `LLM_API_KEY`, `LLM_MODEL` 중 하나라도 비면 `503 llm_not_configured`다.
- 대상 보고서는 조회 가능한 `draft`여야 한다. 제출된 보고서는 `409 report_not_editable`이다.
- 시작은 `202`와 `Location`, `Retry-After`를 반환하고 클라이언트는 `GET /api/agent-runs/{agent_run_id}`로 polling한다.
- `idempotency_key`는 필수다. 같은 요청자가 같은 키로 다시 보내면 새 실행을 만들지 않고 기존 실행을 돌려준다.
- 결과는 제안일 뿐이다. `output_snapshot`에만 남고 `report.content`는 사람이 `PATCH /api/reports/{report_id}`로 확정하기 전까지 바뀌지 않는다.
- 실행이 실패해도 조회는 `200`이고 `status_code=failed`와 안전한 오류 코드를 반환한다.
- 오류 코드에는 공급자 URL과 API key를 넣지 않는다. `llm_request_failed:<예외종류>`, `llm_provider_error:<상태>`, `llm_output_schema_mismatch` 형태만 쓴다.
- 실행 이력은 같은 팀 안에서 요청자 본인 것만 조회한다.

### 자료실 업로드와 다운로드

- 자료실은 팀 공유물이다. 같은 팀이면 팀원도 문서를 모두 조회한다.
- 업로드는 `multipart/form-data`만 받는다. JSON base64 업로드는 없다.
- 확장자, 선언 MIME, 실제 파일 signature 셋을 함께 검사한다. 하나라도 어긋나면 거절한다.
- 허용 형식은 멀티에이전트 운영 플로우의 자료실 입력인 `.pdf`, `.docx`, `.pptx`다. 실행 파일, 압축 파일과 HTML 은 받지 않는다.
- 형식 위반은 `415`, 크기 초과는 `413`, 빈 파일과 잘못된 파일명은 `422`다.
- 저장 경로는 서버가 만든다. 원본 파일명을 경로에 쓰지 않고 표시용으로만 보관한다.
- `storage_key`는 어떤 응답에도 넣지 않는다. 다운로드는 매 요청마다 팀 권한을 검사한 뒤 짧게 사는 서명 URL을 발급한다.
- 버전 번호는 서버가 트랜잭션 안에서 매긴다. 같은 문서에 다시 올리면 `version_no`가 하나 올라간다.
- 저장소에 올린 뒤 DB 기록이 실패하면 올린 객체를 지워 고아를 남기지 않는다.
- 문서 번호는 서버가 `SL-DC-YYYY-####`로 생성한다.
- Storage 설정이 없으면 업로드와 다운로드를 `503 storage_not_configured`로 막는다.
- OCR과 텍스트 추출은 아직 없다. `processing_status`는 업로드 시 `uploaded`로 둔다.

### 영업 딜의 화면 필터와 상태 전이

- 영업현황은 `phase_code`를 보내지 않아 전체 phase를 조회한다.
- 견적현황은 `phase_code=quote`, 계약현황은 `phase_code=contract`, 발주현황은 `phase_code=order`를 반복 Query 값으로 보낸다.
- 단계명이나 순번을 phase로 추정하지 않는다. `SalesDealRead.sales_pipeline_stage_phase_code`를 사용한다.
- 신규 딜 번호는 서버가 `SL-DL-YYYY-####`로 생성한다. 기존 `FM-CT-*` 번호는 데이터 보존을 위해 그대로 조회될 수 있다.
- 신규 딜은 published 파이프라인과 그 소속 단계를 명시한다. archived 파이프라인에는 새 딜을 만들 수 없다.
- archived 단계는 기존 딜 조회와 단계 표시에는 남지만 생성·이동 대상 조회에서는 `404 sales_pipeline_stage_not_found`다.
- 같은 파이프라인 안에서 단계가 바뀌면 `closed` phase에서만 `closed_on`을 오늘로 설정하고, confirmed contract 단계 최초 진입 시 비어 있는 `contract_signed_on`을 오늘로 설정한다.
- 발주 생성은 연결 딜을 해당 파이프라인의 첫 `order` phase 단계로 이동한다.
- 신규 발주와 발주의 딜 재연결은 published 파이프라인 딜만 허용한다. archived 딜에 연결된 기존 발주의 조회와 딜 ID를 바꾸지 않는 수정은 유지한다.

현재 영업·발주 API의 안정적인 업무 오류 코드는 다음과 같다.

- 공통 범위: `scope_not_allowed`, `deal_not_found`, `order_not_found`, 각 `*_not_found`
- 설정·관계: `sales_pipeline_not_found`, `sales_pipeline_stage_not_found`, `sales_deal_type_code_not_found`, `purchase_order_status_code_not_found`, `sales_pipeline_stage_pipeline_mismatch`, `contact_company_mismatch`, `contact_owner_mismatch`
- 검증: `invalid_sales_deal_dates`, `invalid_order_dates`, `invalid_sales_deal_position`, `sales_pipeline_order_stage_not_found`
- 충돌: `invalid_state_transition`, `sales_deal_conflict`, `order_conflict`, `sales_deal_number_exhausted`, `order_number_exhausted`

## 18. 대시보드 구현 요구사항

- 대시보드 KPI의 기준일은 `Asia/Seoul`의 오늘이다.
- 일정 목록의 기준일은 사용자가 선택한 날짜이며 생략하면 오늘이다.
- 담당자 범위는 4절의 `owner_member_id` 규칙을 사용하고 모든 카드, 주간 집계와 일정 목록에 동일하게 적용한다.
- 공지는 팀 공개 범위이며, 개인 지시는 로그인한 수신자 범위다. 둘 다 담당자 선택과 무관하다.
- 공지와 지시는 전체 수와 최신 항목 3개를 첫 응답에 포함한다. 3개보다 적으면 있는 만큼 반환한다.
- 공지 항목에는 ID, 제목, 본문, 작성자와 게시 시각이 필요하다.
- 지시 항목에는 ID, 제목, 본문, 작성자, 게시 시각, nullable `due_at`과 작성자 원문 `due_text`가 필요하다.
- 대시보드의 증가형 목록은 7절의 `skip`, `limit` 규칙을 따르되 `limit`은 최대 30이며, 초과하면 `422`를 반환한다.

| 화면 영역 | 집계 계약 |
|---|---|
| 방문 회사 | 오늘의 외부 활동에 연결된 고객사를 중복 없이 센다. |
| 전체 일정 | 오늘의 미팅과 내부 업무를 모두 센다. |
| 미완료 후속업무 | 미완료 전체, 지연, 기준일부터 7일 이내 마감 건수를 같은 범위로 계산한다. |
| C/S 요청 | 완료를 포함한 전체, 처리 중, 긴급 건수를 같은 범위로 계산한다. |
| 계약갱신 | `confirmed` 영업 딜의 계약 종료일을 기준으로 대상 수, 대표 고객사와 나머지 고객사 수를 반환한다. |
| 매출 목표 | 목표 월, 목표 금액, 확정 매출액과 달성률을 반환한다. |
| 주간 일정 | 화면에 표시할 시작일·종료일과 7일 각각의 일정 수·납기 수를 반환한다. 납기는 발주의 `expected_receipt_on`을 기준으로 센다. |

### 대시보드 응답 규칙

- `GET /api/dashboard` 하나로 카드 집계와 주간 밴드를 반환한다. 오늘 일정 목록은 `GET /api/activities`를 쓴다.
- 한 요청의 모든 집계는 요청 시작 시각에 고정한 `as_of` 하나를 기준으로 한다.
- 카드 숫자는 같은 조건의 목록 API `total`과 일치해야 한다. 구현은 각 도메인 라우터의 조회 범위 조건을 그대로 재사용한다.
- 주간 밴드는 기준일이 셋째 칸에 오는 7일이며 `days`는 항상 7개다.
- 계약갱신 항목은 계약 종료일과 계약서 번호를 함께 반환한다. `새봄정형외과 외 1곳` 같은 문장은 프론트가 조합한다.
- 갱신 기준 일수는 서버가 정하지 않는다. `renewal_within_days`를 준 요청만 그 창으로 거르고, 생략하면 기준일 이후 만료 예정 전체를 센다. 응답의 `within_days`는 적용한 값이며 생략 시 `null`이다.
- 매출 목표는 계약 상태를 구분해 확정 금액과 진행 중 금액을 함께 반환한다. 달성률은 확정 금액 기준이며 목표가 없으면 `null`이다.
- 공지와 개인 지시는 담당자 범위와 무관하다. `owner_member_id`를 적용하지 않는다.
| 선택 날짜 일정 | 미팅 목록과 업무 목록, 각각의 전체 수를 반환한다. |

매출 목표는 다음과 같이 계산한다.

- 목표 월은 요청값이 없으면 오늘이 속한 월이다.
- 목표 금액은 같은 목표 월과 담당자 범위에 속한 `sales_target.target_amount`의 합계다.
- 확정 매출액은 `contract_signed_on`이 목표 월에 속하고 `outcome_code=confirmed` 단계에 있는 미삭제 `sales_deal.deal_amount`의 합계다. `closed_on`은 closed phase의 종료일이므로 매출 귀속일로 사용하지 않는다.
- 달성률은 `확정 매출액 / 목표 금액 * 100`을 소수점 첫째 자리로 반올림하며 100으로 제한하지 않는다. 목표가 없거나 합계가 0이면 `null`이다.

선택 날짜 일정의 각 항목에는 다음 값이 필요하다.

- ID, 미팅·업무 구분, 시작·종료 시각, 제목과 완료 상태
- 영업 단계 또는 업무 상태가 있으면 해당 상태
- 고객사, 고객 담당자와 장소가 있으면 해당 정보
- 한 줄 브리핑
- 연결된 보고서가 있으면 보고서 ID와 작성 상태

대시보드 구현은 다음을 검증한다.

- 공지·지시 전체 수와 추가 조회 가능한 항목 수가 일치한다.
- 항목이 3개 이상이면 첫 응답에 공지와 지시를 각각 3개 포함한다.
- 같은 고객사의 외부 활동이 여러 개여도 방문 회사는 한 번만 센다.
- 카드 집계와 같은 조건의 상세 목록 `total`이 일치한다.
- 날짜별 일정 수는 같은 날짜 일정 목록의 `total`과, 납기 수는 같은 날짜의 발주 목록 `total`과 일치한다.
- 팀원, 팀장 단일 선택, 팀장 복수 선택과 팀 전체 범위를 각각 검증한다.
