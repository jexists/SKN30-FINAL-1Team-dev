# SalesLuv Supabase Auth 전환 및 백엔드 장애 대응 구현 프롬프트

현재 SalesLuv의 자체 로그인 방식을 Supabase Auth 기반으로 전환하고, 백엔드 장애가 프론트 전체를 가리지 않도록 수정해줘.

작업 전 `AGENTS.md`와 관련 코드를 읽고 현재 변경사항을 확인한다. 요청 범위 밖 코드는 건드리지 말고, 원격 Supabase에 SQL을 적용하거나 Auth 사용자를 생성·삭제하지 않는다. 필요한 SQL과 스크립트만 저장소에 작성하고 실제 적용은 별도 승인 후 진행한다. 커밋·푸시하지 않는다.

## 현재 문제

- Supabase는 PostgreSQL로만 사용하고 있다.
- `member.login_id`, `member.password_hash`를 직접 조회하고 검증한다.
- `SESSION_SECRET`으로 자체 세션 쿠키를 만든다.
- 테스트 계정 이메일과 비밀번호를 `backend/.env`에 보관한다.
- 프론트 `SessionProvider`는 `/auth/me` 호출이 실패하면 앱 전체를 서버 연결 오류 화면으로 교체한다.
- 프론트는 Supabase에 직접 연결하면 안 되며 인증 요청도 반드시 FastAPI 백엔드를 통과해야 한다.

## 1. Supabase Auth 기반 인증·세션

다음 구조로 변경한다.

```text
React
→ FastAPI 인증 API
→ Supabase Auth
→ FastAPI가 인증 결과 검증
→ public.member에서 팀·역할·활성 상태 확인
```

### 인증 원칙

- 프론트에는 Supabase SDK, publishable key, secret key를 추가하지 않는다.
- 이메일과 비밀번호는 프론트에서 FastAPI `/api/auth/login`으로만 전달한다.
- 백엔드가 Supabase Auth의 password login API를 호출한다.
- 비밀번호는 저장하거나 로그에 출력하지 않는다.
- Supabase가 발급한 access token과 refresh token은 각각 `HttpOnly` 쿠키로 관리한다.
- 쿠키는 운영 환경에서 `Secure`, `SameSite=Lax`, API 범위의 적절한 `Path`를 사용한다.
- 자체 JWT/HMAC 토큰을 추가로 만들지 않는다.
- Supabase secret key는 브라우저로 전달하지 않는다.

### 인증 API

기존 경로를 최대한 유지한다.

- `POST /api/auth/login`
  - 이메일·비밀번호를 Supabase Auth에 전달한다.
  - 성공하면 Supabase access/refresh token을 `HttpOnly` 쿠키로 저장한다.
  - 연결된 `member` 정보를 반환한다.
- `POST /api/auth/refresh`
  - refresh token 쿠키로 Supabase 세션을 갱신한다.
  - 회전된 토큰을 다시 쿠키에 저장한다.
- `GET /api/auth/me`
  - access token을 Supabase에서 검증한다.
  - 검증된 Supabase 사용자 UUID로 `member`를 조회한다.
- `POST /api/auth/logout`
  - 가능한 경우 Supabase 세션을 종료한다.
  - Supabase 호출 실패 여부와 관계없이 로컬 쿠키는 반드시 삭제한다.

프론트 Axios 클라이언트는 인증 API를 포함해 모든 호출을 백엔드로만 보낸다. access token 만료로 401이 발생하면 refresh 요청을 한 번만 수행하고 원래 요청을 한 번 재시도한다. 여러 요청이 동시에 실패해도 refresh 요청은 하나만 실행되도록 한다. refresh 실패 시 로그인 상태를 해제한다.

### 사용자와 `member` 연결

새 SQL 파일을 추가한다. 기존 적용 SQL은 수정하지 않는다.

```text
public.member.auth_user_id UUID
    UNIQUE
    REFERENCES auth.users(id)
```

- `auth_user_id`는 로그인하지 않는 목업용 팀원도 있으므로 nullable로 둔다.
- Supabase에서 검증한 `auth.users.id`와 `member.auth_user_id`가 일치해야 로그인할 수 있다.
- 팀, 역할, 활성 상태의 기준은 `member.team_id`, `member.role_code`, `member.active`다.
- 사용자가 수정할 수 있는 `user_metadata`를 권한 판단에 사용하지 않는다.
- 연결되지 않은 사용자, 비활성 사용자, 허용되지 않은 역할은 인증을 거부한다.
- 계정 존재 여부가 노출되지 않도록 로그인 실패 응답을 통일한다.

전환 후 사용하지 않는 항목을 제거한다.

- `member.login_id`
- `member.password_hash`
- 자체 password hash/verify 코드
- 자체 session token 생성·검증 코드
- `SESSION_SECRET`
- `SESSION_TTL_SECONDS`
- 자체 로그인 계정용 rate-limit 설정과 코드
- 모든 `DEMO_*_LOGIN_ID`
- `DEMO_PASSWORD`

단, 기존 Storage에서 사용하는 `SUPABASE_SECRET_KEY`, `SUPABASE_STORAGE_BUCKET`은 제거하지 않는다. Auth password login에는 secret key 대신 백엔드 전용 `SUPABASE_PUBLISHABLE_KEY`를 사용한다. 필요한 최소 HTTP 호출만 구현하고 무거운 Supabase 전체 SDK가 필요하지 않으면 추가하지 않는다.

## 2. 백엔드 장애 시 프론트 처리

백엔드가 꺼져 있어도 React 앱과 로그인 화면은 정상적으로 렌더되어야 한다.

현재 `SessionProvider`의 다음 동작을 제거한다.

- `/auth/me` 실패 시 앱 전체를 `<main role="alert">`로 교체하는 동작
- 서버 응답을 기다리며 화면을 계속 `null`로 유지하는 동작

세션 상태를 최소한 다음과 같이 구분한다.

```text
loading
authenticated
unauthenticated
unavailable
```

동작 기준:

- `/auth/me`의 401은 정상적인 비로그인 상태다.
- 네트워크 오류, timeout, 5xx는 백엔드 연결 실패 상태다.
- 백엔드 연결 실패를 401처럼 처리하거나 가짜 로그인 세션을 만들지 않는다.
- 아직 검증된 세션이 없다면 로그인 화면을 표시한다.
- 이미 검증된 세션으로 앱을 보고 있다가 백엔드가 중단되면 현재 화면은 유지하되 API 작업은 실패 처리한다.
- 백엔드 확인 없이 보호된 실제 데이터나 쓰기 작업을 허용하지 않는다.
- 기존 `frontend/src/components/Modal`을 재사용해 다음 내용을 표시한다.
  - 제목: `서버에 연결할 수 없습니다`
  - 설명: `백엔드 서버 상태를 확인한 뒤 다시 시도해 주세요.`
  - `다시 시도` 버튼
  - `닫기` 버튼
- 모달을 닫아도 프론트 화면은 남아 있어야 한다.
- 로그인 요청 중 백엔드가 끊긴 경우에도 로그인 페이지를 그대로 유지하고 모달을 표시한다.
- 잘못된 이메일·비밀번호는 기존처럼 입력 영역의 인증 오류로 표시하고 연결 실패 모달과 구분한다.

로그인 입력란은 Supabase password login에 맞게 `이메일`과 `비밀번호`로 변경하고 이메일 입력 타입과 자동완성을 올바르게 지정한다.

## 3. 테스트용 Supabase Auth 계정과 데이터 시나리오

로그인 가능한 테스트 계정은 총 4개다.

| Supabase Auth 사용자 | 연결 팀 | 역할 | 데이터 상태 |
|---|---|---|---|
| filled manager | 목업 데이터 팀 | manager | 기존 목업 데이터 있음 |
| filled member | 목업 데이터 팀 | member | 기존 목업 데이터 있음 |
| empty manager | 최초 설정 팀 | manager | 초기 설정 상태 |
| empty member | 최초 설정 팀 | member | 초기 설정 상태 |

계정 이메일, 비밀번호, Supabase 사용자 UUID를 `.env`나 저장소 파일에 저장하지 않는다.

- 이메일과 비밀번호는 Supabase Authentication에서만 관리한다.
- 사용자 UUID는 Supabase가 생성한다.
- 실제 테스트 사용자 4명은 Supabase Dashboard 또는 승인된 관리자 작업으로 별도 생성한다.
- 기존 고정 팀 UUID와 `member` UUID는 다른 목업 데이터의 FK가 참조하므로 유지한다.
- 기존 두 번째 팀원 등 로그인하지 않는 목업 구성원은 삭제하지 않고 `auth_user_id = NULL`로 유지할 수 있다.

`seed_demo_auth.py`는 더 이상 계정 이메일이나 비밀번호를 생성·해시하지 않도록 변경한다.

- 팀, `member`, 기본 설정, 파이프라인 데이터만 반복 실행 가능하게 seed한다.
- 별도 연결 명령은 Supabase Dashboard에서 확인한 사용자 UUID 4개를 CLI 인자로 받아 기존 `member`에 연결한다.
- UUID를 `.env`에 요구하지 않는다.
- 비밀번호나 이메일을 입력받거나 출력하지 않는다.
- 네 역할 중 중복·누락·잘못된 UUID가 있으면 변경 전에 명확히 실패한다.
- `--dry-run` 또는 이에 준하는 읽기 전용 확인 방법을 제공한다.
- 원격 DB에는 자동 실행하지 않는다.

## 오류 응답 기준

- 잘못된 이메일·비밀번호: 401
- access/refresh token 없음 또는 만료: 401
- Supabase 계정은 있지만 연결된 `member`가 없음: 403
- 비활성 `member` 또는 잘못된 역할: 403
- Supabase Auth/백엔드 의존 서비스 연결 실패: 503
- 응답과 로그에 토큰, 비밀번호, secret key를 포함하지 않는다.

## 테스트와 완료 조건

백엔드 테스트에서는 실제 Supabase 네트워크를 호출하지 말고 HTTP 응답을 mock한다.

필수 테스트:

1. Supabase 로그인 성공 후 두 `HttpOnly` 쿠키가 설정된다.
2. 잘못된 인증 정보는 401이다.
3. 정상 토큰이 올바른 `member.auth_user_id`에 연결된다.
4. 연결되지 않은 사용자와 비활성 `member`는 거부된다.
5. 만료된 access token이 refresh 후 정상 복구된다.
6. refresh 실패 시 쿠키가 제거된다.
7. logout은 Supabase 장애 시에도 쿠키를 제거한다.
8. Supabase 장애는 503으로 변환된다.
9. 네 테스트 역할이 올바른 팀·역할·목업 프로필에 연결된다.
10. seed/link 명령의 반복 실행 결과가 동일하다.

프론트에는 새 테스트 프레임워크를 추가하지 않는다. 다음 검사를 실행한다.

- backend pytest
- backend ruff
- frontend typecheck
- frontend lint
- frontend build
- 기존 mock 정합성 검사

수동 확인:

1. 백엔드를 끄고 프론트만 실행해도 로그인 화면이 보인다.
2. 서버 연결 오류 모달을 닫고 다시 열거나 재시도할 수 있다.
3. 네 Supabase 계정으로 로그인하면 각각 올바른 팀·역할·데이터 상태가 표시된다.
4. 로그인 후 백엔드를 중단해도 현재 화면이 사라지지 않는다.
5. 보호 API의 읽기·쓰기 요청은 백엔드 검증 없이 성공하지 않는다.

## 범위 제한

- 공개 회원가입 UI는 만들지 않는다.
- 팀원 초대 기능은 이번 작업에 포함하지 않는다.
- 프론트에서 Supabase Auth를 직접 호출하지 않는다.
- 원격 Supabase 사용자 생성, SQL 적용, 데이터 삭제는 하지 않는다.
- 새 인증 프레임워크나 불필요한 추상화를 추가하지 않는다.

마지막에 변경 파일, 인증 흐름, 실행한 검사, 원격에 별도로 적용해야 할 SQL 및 Supabase Dashboard 작업을 요약해서 보고한다.

## 참고 문서

- [Supabase Auth 개요](https://supabase.com/docs/guides/auth)
- [Supabase Auth 사용자 관리](https://supabase.com/docs/guides/auth/users)
- [Supabase password sign-in](https://supabase.com/docs/reference/javascript/auth-signinwithpassword)
