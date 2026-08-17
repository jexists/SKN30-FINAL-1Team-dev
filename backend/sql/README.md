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

SQL은 `0001 → 0002 → 0003 → 0004 → 0005` 순서로 적용합니다. `0005` 적용 전에는 앱의
최종 ORM/API와 물리 스키마가 일치하지 않으므로 데모 seed를 실행하지 않습니다.

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

## 개발 로그인 계정

`backend/.env`의 `DEMO_FILLED_MANAGER_LOGIN_ID`, `DEMO_FILLED_MEMBER_LOGIN_ID`,
`DEMO_FILLED_MEMBER2_LOGIN_ID`, `DEMO_EMPTY_MANAGER_LOGIN_ID`, `DEMO_EMPTY_MEMBER_LOGIN_ID`,
`DEMO_EMPTY_MEMBER2_LOGIN_ID`, `DEMO_PASSWORD`를 채운 뒤 아래 명령을 실행합니다. 평문
비밀번호는 파일이나 로그에 남기지 않고 실행 시 scrypt로 해시합니다.

```bash
cd backend
DEBUG=false uv run python -m scripts.seed_demo_auth
```

고정된 합성 UUID로 데이터가 채워진 팀과 비어 있는 첫 세팅 팀, 각 팀의 팀장·팀원 2명 계정,
팀별 기본 표시 설정과 9단계 기본 published 파이프라인을 upsert하므로 같은 개발 DB에 다시
실행할 수 있습니다.

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
