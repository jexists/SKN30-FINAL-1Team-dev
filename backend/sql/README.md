# DB 변경

현재 자동 마이그레이션 도구와 적용 이력 저장소가 없으므로 이 문서에서 SQL 파일의 적용 이력을 관리합니다.

## 변경 원칙

1. 변경 전 대상 환경과 현재 스키마를 확인합니다.
2. 스키마 변경은 새 `backend/sql/<timestamp>_<description>.sql` 파일로 남깁니다.
3. 병합되었거나 적용된 SQL은 수정하지 않고 후속 파일을 추가합니다.
4. ORM 모델은 매핑된 테이블 구조가 바뀔 때만 함께 수정합니다.
5. seed는 스키마 변경과 분리하고, 합성 데이터로 반복 실행 가능하게 작성합니다.
6. 원격 DB 적용은 명시적으로 요청받은 경우에만 대상 환경을 다시 확인한 뒤 수행하고, 적용한 파일과 결과를 기록합니다.

## 연결 구분

- 현재 앱 세션은 장기 실행 FastAPI 서버용 Supabase session pooler를 기준으로 설정되어 있습니다.
- 스키마 변경과 관리 작업에는 direct 연결을 우선 사용합니다.
- 포트만으로 연결 종류를 단정하지 말고 Supabase의 연결 호스트와 모드를 함께 확인합니다.
- SQL Editor로 실행해도 저장소와 환경별 적용 이력은 자동으로 남지 않으므로 SQL 파일과 적용 기록이 필요합니다.

## 스키마 파일

- `20260817_0001_core_schema.sql`: 일정 저장 흐름에 필요한 팀, 회원, 고객사, 고객 담당자,
  일정, 일정 동행자 6테이블을 먼저 생성합니다.
- `20260817_0002_remaining_schema.sql`: 최종 ERD의 나머지 14테이블과 일정의 상품·계약·발주
  외래키를 추가해 전체 20테이블·200컬럼을 완성하고, 모든 테이블의 RLS를 활성화합니다.
- `20260817_0003_singular_table_names.sql`: 20개 테이블 이름을 단수형으로 변경합니다.
  PostgreSQL 예약어인 `order` 대신 `purchase_order`, 발주 품목은 `purchase_order_item`을 사용합니다.
- `20260817_0004_unique_customer_company_name.sql`: 같은 팀에 같은 이름의 고객사가 중복
  생성되지 않도록 유일 인덱스를 추가합니다.
- `20260817_0005_sales_deal_names.sql`: 기존 `contract`를 영업 시작부터 견적·계약·발주를
  잇는 `sales_deal`로 바꾸고, 저장형 파이프라인과 팀별 표시 설정 5종을 추가합니다. 기존
  행과 UUID를 보존하면서 최종 **26테이블·266컬럼·64개 FK 제약조건**을 완성합니다.
- `20260818_0006_member_auth_user_id.sql`: Supabase Auth 사용자와 구성원을 잇는
  `member.auth_user_id`(nullable, UNIQUE, `auth.users(id)` 참조) 한 컬럼을 추가합니다.
  로그인하지 않는 목업 구성원은 `NULL`로 남습니다. `auth` 스키마 참조 권한이 없어
  FK 생성이 실패하면 FK 없이 `uuid UNIQUE`만 두고 그 사실을 적용 이력에 남깁니다.
- `20260818_0007_drop_member_login_columns.sql`: 자체 로그인 흔적인 `member.login_id`와
  `member.password_hash`를 제거합니다. **적용 보류 상태입니다.** `0006` 적용, 테스트 계정
  4개 연결, 네 계정 로그인 확인을 모두 마친 뒤에만 실행합니다. 되돌릴 수 없습니다.

SQL은 `0001 → 0002 → 0003 → 0004 → 0005 → 0006` 순서로 적용합니다. `0005` 적용 전에는
앱의 최종 ORM/API와 물리 스키마가 일치하지 않으므로 데모 seed를 실행하지 않습니다.
`0007`은 위 조건을 만족한 뒤 별도로 적용합니다.

## 적용 이력

| 적용일 | 대상 | 파일 | 연결 | 결과 |
|---|---|---|---|---|
| 2026-08-17 | 개발 Supabase `public` | `20260817_0001_core_schema.sql` | Session Pooler | 성공 |
| 2026-08-17 | 개발 Supabase `public` | `20260817_0002_remaining_schema.sql` | Session Pooler | 성공 |
| 2026-08-17 | 개발 Supabase `public` | `20260817_0003_singular_table_names.sql` | Session Pooler | 성공 |
| 2026-08-17 | 개발 Supabase `public` | `20260817_0004_unique_customer_company_name.sql` | Session Pooler | 성공 |
| 2026-08-17 | 개발 Supabase `public` | `scripts/seed_demo_auth.py` 초기 2계정 | Session Pooler | 성공 |
| 2026-08-17 | 개발 Supabase `public` | `scripts/seed_demo_auth.py` 2팀·6계정 | Session Pooler | 성공 |
| 2026-08-17 | 개발 Supabase `public` | `scripts/seed_demo_customers.py` 고객사 6개·담당자 32명 | Session Pooler | 성공 |
| 2026-08-17 | 개발 Supabase `public` | `scripts/seed_demo_activities.py` 상품 3개·일정 12건 | Session Pooler | 성공 |
| 2026-08-18 | 개발 Supabase `public` | `20260817_0005_sales_deal_names.sql` | Session Pooler | 성공 |
| 2026-08-18 | 개발 Supabase `public` | `scripts/seed_demo_auth.py` 2팀·6계정 | Session Pooler | 성공 |
| 2026-08-18 | 개발 Supabase `public` | `scripts/seed_demo_customers.py` 고객사 6개·담당자 32명 | Session Pooler | 성공 |
| 2026-08-18 | 개발 Supabase `public` | `scripts/seed_demo_activities.py` 상품 3개·일정 12건 | Session Pooler | 성공 |
| 2026-08-18 | 개발 Supabase `public` | `scripts/seed_demo_sales_deals.py` 딜 61건 | Session Pooler | 성공 |
| 2026-08-18 | 개발 Supabase `public` | `scripts/seed_demo_orders.py` 발주 2건·품목 2건 | Session Pooler | 성공 |
| 2026-08-18 | 개발 Supabase `public` | `scripts/seed_demo_support.py` C/S 요청 3건 | Session Pooler | 성공 |
| 2026-08-18 | 개발 Supabase `public` | `scripts/seed_demo_notices.py` 공지 5건·지시 2건 | Session Pooler | 성공 |
| 2026-08-18 | 개발 Supabase `public` | `20260818_0006_member_auth_user_id.sql` | Session Pooler | 성공 (`auth.users` FK 포함) |
| 2026-08-18 | 개발 Supabase `public` | `scripts/seed_demo_auth.py` 3팀·8계정 | Session Pooler | 성공 |
| 2026-08-18 | 개발 Supabase `public` | `scripts/link_demo_auth_users.py` 테스트팀 2명 연결 | Session Pooler | 성공 |

## 개발 로그인 계정

로그인은 Supabase Auth가 담당합니다. 계정의 이메일과 비밀번호는 Supabase Dashboard에서만
관리하며 `.env`를 포함해 저장소 어디에도 두지 않습니다.

### 1. 구성원과 기본 데이터 seed

고정된 합성 UUID로 데이터가 채워진 팀, 비어 있는 첫 세팅 팀, 비어 있는 테스트팀과 각 팀의
팀장·팀원, 팀별 기본 표시 설정과 9단계 기본 published 파이프라인을 upsert하므로 같은 개발
DB에 다시 실행할 수 있습니다. 이 스크립트는 자격증명을 다루지 않습니다.

```bash
cd backend
DEBUG=false uv run python -m scripts.seed_demo_auth
```

### 2. Supabase Auth 사용자 생성

Supabase Dashboard > Authentication > Users > Add user > Create new user에서 만듭니다.
**Auto Confirm User를 켜면** 확인 메일을 보내지 않으므로 수신 가능한 주소가 아니어도 됩니다.

| 역할 | 연결 팀 | 데이터 상태 |
|---|---|---|
| filled manager | SalesLuv 데모팀 | 기존 목업 데이터 있음 |
| filled member | SalesLuv 데모팀 | 기존 목업 데이터 있음 |
| empty manager | SalesLuv 첫 세팅팀 | 초기 설정 상태 |
| empty member | SalesLuv 첫 세팅팀 | 초기 설정 상태 |
| test manager | SalesLuv 테스트팀 | 초기 설정 상태 |
| test member | SalesLuv 테스트팀 | 초기 설정 상태 |

데이터가 있는 팀과 첫 세팅 팀의 두 번째 팀원(이수민)은 로그인하지 않으므로 계정을 만들지
않고 `auth_user_id = NULL`로 둡니다.

### 3. 사용자와 구성원 연결

생성된 사용자의 UID를 Dashboard에서 복사해 인자로 넘깁니다. UID를 `.env`에 두지 않습니다.
연결할 역할만 골라 주면 되고, 주지 않은 역할의 구성원은 건드리지 않습니다.

```bash
cd backend
uv run python -m scripts.link_demo_auth_users --dry-run \
    --filled-manager <UUID> --filled-member <UUID> \
    --empty-manager  <UUID> --empty-member  <UUID> \
    --test-manager   <UUID> --test-member   <UUID>
```

`--dry-run`으로 바뀔 내용을 확인한 뒤 플래그를 빼고 다시 실행합니다. 중복·누락·형식 오류가
있으면 DB를 건드리기 전에 중단하며, 같은 인자로 여러 번 실행해도 결과는 같습니다.

프론트 목업과 같은 합성 고객 데이터는 인증 seed 다음에 실행합니다. 데이터가 있는 팀에만
고객사와 담당자를 upsert하고 첫 세팅 팀은 건드리지 않습니다.

```bash
cd backend
DEBUG=false uv run python -m scripts.seed_demo_customers
```

일정 seed는 인증과 고객 seed를 차례로 실행한 뒤 적용합니다. 데이터가 있는 팀에만 고정
합성 상품 3개와 일정 12건을 upsert하고 첫 세팅 팀은 건드리지 않습니다.

```bash
cd backend
DEBUG=false uv run python -m scripts.seed_demo_activities
```

영업 딜 seed는 인증·고객·일정 seed를 차례로 실행한 뒤 적용합니다. 데이터가 있는 팀의
9단계 기본 영업 파이프라인과 기존 상품 3종에 연결되는 합성 영업 딜 61건을 upsert합니다.
별도 상품이 필요한 프론트 목업 50건은 넣지 않으며 첫 세팅 팀은 건드리지 않습니다.

```bash
cd backend
DEBUG=false uv run python -m scripts.seed_demo_sales_deals
```

발주 seed는 인증·고객·일정·영업 딜 seed를 차례로 실행한 뒤 적용합니다. 데이터가 있는 팀에만
현재 고객사·상품·영업 딜 관계가 모두 정확한 합성 발주 2건과 품목 2건을 upsert합니다. 관계가
누락되거나 불일치하는 나머지 프론트 목업 발주 3건은 넣지 않으며 비어 있는 팀은 건드리지 않습니다.

```bash
cd backend
DEBUG=false uv run python -m scripts.seed_demo_orders
```

C/S seed는 인증·고객 seed를 차례로 실행한 뒤 적용합니다. 데이터가 있는 팀에만 고객사,
접수자, 담당자가 정확히 연결되는 합성 C/S 요청 3건을 upsert합니다. 접수자가 없는 나머지
프론트 목업 1건은 넣지 않고, 별도 대응 이력이 없어 답변 이력도 만들지 않으며 비어 있는
팀은 건드리지 않습니다.

```bash
cd backend
DEBUG=false uv run python -m scripts.seed_demo_support
```

공지 seed는 인증 seed를 실행한 뒤 적용합니다. 데이터가 있는 팀에만 팀 공지 5건과 팀원
한 명에게 가는 개인 지시 2건을 upsert합니다. 수신자가 없는 행이 팀 공지, 수신자가 있는
행이 개인 지시이며 비어 있는 팀은 건드리지 않습니다.

```bash
cd backend
DEBUG=false uv run python -m scripts.seed_demo_notices
```
