# DB 변경

현재 자동 마이그레이션 도구와 적용 이력 저장소가 없으므로 이 문서에서 SQL 파일의 적용 이력을 관리합니다.

## 변경 원칙

1. 변경 전 대상 환경과 현재 스키마를 확인합니다.
2. 스키마 변경은 새 `backend/sql/<timestamp>_<description>.sql` 파일로 남깁니다.
3. 병합되었거나 적용된 SQL은 수정하지 않고 후속 파일을 추가합니다.
4. ORM 모델은 매핑된 테이블 구조가 바뀔 때만 함께 수정합니다.
5. seed는 스키마 변경과 분리하고, 합성 데이터로 반복 실행 가능하게 작성합니다.
6. 원격 DB 적용은 명시적으로 요청받은 경우에만 대상 환경을 다시 확인한 뒤 수행하고, 적용한 파일과 결과를 기록합니다.

> **원칙 3의 예외 (2026-08-19).** Supabase Auth 전환으로 `member`의 PK 의미가 바뀌면서
> (`member.id` = `auth.users.id`) 후속 파일을 덧붙이는 방식으로는 정리할 수 없게 되었습니다.
> 개발 DB에 보존할 데이터가 없었으므로 기존 SQL 7개(`0001`~`0007`)를 지우고 baseline 한
> 파일로 합치고 적용 이력을 리셋했습니다. 원칙 3은 이후 변경부터 다시 적용됩니다.

## 연결 구분

- 현재 앱 세션은 장기 실행 FastAPI 서버용 Supabase session pooler를 기준으로 설정되어 있습니다.
- 스키마 변경과 관리 작업에는 direct 연결을 우선 사용합니다.
- 포트만으로 연결 종류를 단정하지 말고 Supabase의 연결 호스트와 모드를 함께 확인합니다.
- SQL Editor로 실행해도 저장소와 환경별 적용 이력은 자동으로 남지 않으므로 SQL 파일과 적용 기록이 필요합니다.

## 스키마 파일

- `20260819_0001_baseline_schema.sql`: 최종 ERD 전체를 한 파일로 만듭니다.
  **26테이블 · 264컬럼 · 외래키 65개**(public 대상 64개 + `member.id` → `auth.users(id)` 1개).
  로그인은 Supabase Auth가 담당하며 `member` 행 하나가 auth 사용자 하나입니다. 별도 연결
  컬럼 없이 PK 자체를 `auth.users.id`로 맞추므로 `login_id`, `password_hash`,
  `auth_user_id`는 존재하지 않습니다.
  제약조건 이름은 옛 SQL이 남긴 복수형 흔적(`members_pkey` 등) 대신 단수 테이블명을 따릅니다.
  다만 `app/models/sales.py`가 이름으로 참조하는 네 개(`sales_pipeline_stage_*_key` 3개와
  `sales_deal_sales_pipeline_stage_membership_fkey`)는 그대로 유지합니다.

- `20260823_0002_admin_account_provisioning.sql`: `/admin` 계정 발급 화면이 쓰는 컬럼을 더합니다.
  `team`에 `company_name`, `department`, `business_no`(하이픈 없는 10자리), `member`에 `email`을
  추가하고 `member(lower(email))`에 부분 유일 인덱스를 겁니다. `email`의 주인은 여전히
  `auth.users`이며 여기 값은 어드민 목록 표시용 사본입니다. 권한 판단에는 쓰지 않습니다.

- `20260824_0003_customer_contact_assignees.sql`: 고객 담당자를 여러 명 둘 수 있게 합니다.
  `customer_contact`에 `created_by_member_id`(등록한 사람)를 더하고, 담당자 전체를 담는
  `customer_contact_assignee` 테이블을 만듭니다. 기존 `owner_member_id`는 대표 담당자로 남습니다.
  `customers`·`support`·`activities`·`sales_deals`의 조회 스코프가 이 컬럼을 보기 때문입니다.
  기존 행은 `owner_member_id`로 등록자와 담당자를 백필합니다.
  `customer_company`에는 `business_no`(하이픈 없는 10자리)를 더해 같은 이름의 고객사를 구분합니다.

- `20260824_0004_customer_contact_visited.sql`: `customer_contact`에 `visited`(boolean, 기본 false)를
  더합니다. 고객 목록에서 방문·미방문을 한눈에 가르기 위한 값이며 담당자가 직접 바꿉니다.
  활동 기록에서 자동으로 갱신하지 않습니다. 기존 행은 기본값대로 전부 미방문이 됩니다.

`20260819_0001`은 빈 `public` 스키마에 처음부터 만드는 것을 전제로 합니다. 되돌리는 마이그레이션이
아니므로 적용 전에 아래 런북의 1~2단계를 먼저 수행합니다.

## 적용 이력

| 적용일 | 대상 | 파일 | 연결 | 결과 |
|---|---|---|---|---|
| 2026-08-19 | 개발 | (런북 1단계) 26테이블 `DROP TABLE ... CASCADE` | session pooler | 성공. public 테이블 0개 |
| 2026-08-19 | 개발 | `20260819_0001_baseline_schema.sql` | session pooler | 성공. 26테이블 / 264컬럼 / FK 65 / RLS 26 |
| 2026-08-23 | 개발 | `20260823_0002_admin_account_provisioning.sql` | session pooler | 성공. team +3컬럼 / member +1컬럼 / 부분 유일 인덱스 1. 기존 1팀 2명 그대로 |
| 2026-08-24 | 개발 | `20260824_0003_customer_contact_assignees.sql` | session pooler | 성공. customer_company +1컬럼 / customer_contact +1컬럼 / customer_contact_assignee 신설(RLS on). 기존 고객 2건의 등록자·담당자를 owner_member_id 로 백필 |
| 2026-08-24 | 개발 | `20260824_0004_customer_contact_visited.sql` | session pooler | 성공. customer_contact +1컬럼(`visited` boolean NOT NULL DEFAULT false). 기존 고객 2건 모두 기본값대로 미방문 |

## 개발 DB 재구축 런북

로그인은 Supabase Auth가 담당합니다. 계정의 이메일과 비밀번호는 저장소 어디에도 두지 않습니다.

`20260823_0002` 적용 이후 일반 계정은 `/admin` 화면에서 발급합니다. 어드민이 이메일과 팀을 넣으면
Supabase 사용자 생성·초대 메일 발송·`team`/`member` 행 등록이 한 번에 끝나고, 받는 사람이 메일
링크에서 비밀번호를 직접 정합니다. Dashboard에서 직접 만드는 것은 아래 재구축 런북과 어드민
계정 자신에게만 해당합니다.

현재 개발 계정은 두 개입니다.

| 계정 | 이름 | 역할 | 팀 |
|---|---|---|---|
| `teamjang@naver.com` | 김서현 | manager | SalesLuv 데모팀 |
| `teamwon@naver.com` | 김지훈 | member | SalesLuv 데모팀 |

### 1단계. 기존 테이블 삭제

`member` 행이 남아 있으면 `auth.users` FK 때문에 Supabase 사용자를 지울 수 없으므로
테이블을 먼저 지웁니다. `DROP SCHEMA public CASCADE`는 Supabase가 걸어둔 스키마 권한
부여까지 날리므로 사용하지 않습니다.

```sql
DROP TABLE IF EXISTS
    public.agent_run,
    public.file,
    public.document,
    public.report_activity,
    public.report,
    public.sales_target,
    public.support_response,
    public.support_request,
    public.notice,
    public.activity_companion,
    public.activity,
    public.purchase_order_item,
    public.purchase_order,
    public.sales_deal,
    public.customer_contact,
    public.product,
    public.sales_pipeline_stage,
    public.sales_pipeline,
    public.purchase_order_status,
    public.sales_deal_type,
    public.activity_action_tag,
    public.activity_category,
    public.customer_contact_status,
    public.customer_company,
    public.member,
    public.team
CASCADE;
```

### 2단계. Supabase 사용자 정리

Dashboard > Authentication > Users에서 `teamjang@naver.com`과 `teamwon@naver.com`
두 개만 남기고 나머지를 삭제합니다. 계정을 새로 만들어야 하면 Add user > Create new user에서
**Auto Confirm User를 켭니다.** 확인 메일을 보내지 않으므로 수신 가능한 주소가 아니어도 됩니다.

### 3단계. baseline 적용

SQL Editor(direct 연결)에서 `20260819_0001_baseline_schema.sql`을 실행합니다.

### 4단계. 사용자 UID 확인

Dashboard의 사용자 목록에서 두 계정의 UID를 복사합니다. UID는 자격증명이 아니지만 환경에
종속된 값이므로 `.env`나 저장소에 두지 않고 다음 단계의 인자로만 넘깁니다.

### 5단계. 팀·구성원·기본 설정 seed

팀 하나, 구성원 두 명, 팀별 기본 표시 설정 5종과 9단계 기본 published 파이프라인을
upsert하므로 같은 개발 DB에 다시 실행할 수 있습니다. 이 스크립트는 자격증명을 다루지 않습니다.

```bash
cd backend
DEBUG=false uv run python -m scripts.seed_demo_auth --dry-run \
    --manager <teamjang UID> --member <teamwon UID>
DEBUG=false uv run python -m scripts.seed_demo_auth \
    --manager <teamjang UID> --member <teamwon UID>
```

`--dry-run`으로 어떤 UID가 어떤 이름·역할로 들어가는지 확인한 뒤 플래그를 빼고 다시
실행합니다. UUID 형식 오류나 두 역할에 같은 UUID를 준 경우에는 DB를 건드리기 전에 중단하며,
같은 인자로 여러 번 실행해도 결과는 같습니다. `auth.users`에 없는 UID를 주면 외래키에 막혀
어떤 UID가 문제인지 함께 안내합니다.

### 6단계. 검증

```bash
cd backend
DEBUG=false uv run pytest tests/test_models.py
```

`test_models_match_configured_database`가 ORM과 물리 스키마의 테이블·컬럼·nullable·타입·
기본값·PK·FK를 대조합니다. CHECK 제약과 인덱스, RLS는 이 테스트가 보지 않으므로 스키마를
크게 바꿀 때는 카탈로그를 직접 비교합니다.

이후 `teamjang@naver.com`으로 로그인해 `GET /api/auth/me`의 `id`가 Dashboard UID와 같고
`role_code`가 `manager`인지 확인합니다. `teamwon@naver.com`은 같은 `team_id`에 `member`로
나와야 합니다.

### 주의

Dashboard에서 사용자를 지우려면 대응하는 `member` 행(그리고 그 구성원을 참조하는 데이터)을
먼저 지워야 `member.id → auth.users(id)` 외래키에 막히지 않습니다.
