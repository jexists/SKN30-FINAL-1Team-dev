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

<!-- - `20260824_0004_customer_contact_visited.sql`: `customer_contact`에 `visited`(boolean, 기본 false)를
  더합니다. 고객 목록에서 방문·미방문을 한눈에 가르기 위한 값이며 담당자가 직접 바꿉니다.
  활동 기록에서 자동으로 갱신하지 않습니다. 기존 행은 기본값대로 전부 미방문이 됩니다. -->
- `20260824_0004_product_fields.sql`: 상품 등록 화면(`/products`, 팀장 전용)이 받는 항목을
  `product`에 더합니다. `category_code`(system/probe/consumable), `unit_price`(원 단위 정수),
  `shelf_life_months`(유효기간 개월), `memo`, `image_storage_key`입니다. 기존 행은 백필용
  default로 채운 뒤 default를 떼므로 이후 INSERT는 앱이 값을 직접 넣어야 합니다.
  `image_storage_key`는 `notice.image_storage_key`와 같은 뜻이며 API 응답에 나가지 않습니다.
  상품 목록(`GET /api/products`)은 발주·영업 화면이 함께 쓰므로 팀원에게도 그대로 열려 있고,
  쓰기(`POST /api/products`, 사진 업로드)만 팀장으로 제한합니다.
- `20260825_0005_one_manager_per_team.sql`: `member(team_id)`에 `role_code = 'manager' AND active`
  조건의 부분 유일 인덱스를 걸어 팀당 활성 팀장을 한 명으로 제한합니다. `/admin` 계정 발급도
  발급 전에 같은 조건으로 막고 409 `team_manager_exists`를 냅니다. 앱 검사는 안내용이고
  동시 요청까지 막는 근거는 이 인덱스입니다. 물러난 팀장(`active = false`)은 세지 않습니다.

- `20260825_0005_notice_management.sql`: 공지·지시사항을 팀장이 직접 관리하게 합니다.
  `notice`에 `type`(NOTICE/DIRECTIVE), `display_start_date`·`display_end_date`(date, 양끝 포함),
  `is_hidden`, `sort_order`, `updated_at`, `deleted_at`을 더하고 **`recipient_member_id`를 뗍니다.**
  수신자는 지시 하나에 여러 명이 붙을 수 있으므로 `notice_target` 매핑 테이블로 옮깁니다.
  기존 행은 수신자 유무로 `type`을, 게시 시각의 서울 날짜로 `display_start_date`를 백필하고
  종료일은 비워 무기한으로 둡니다. 본문(`body`)은 이제 편집기가 만든 HTML이며
  `app/services/html_sanitize.py`가 허용한 태그만 남깁니다. 본문에 넣은 사진은
  `notice_image`가 가리키는 저장소 객체이고, 본문에는 `/notice-images/{id}`만 박힙니다.
  `storage_key`는 `notice.image_storage_key`와 같은 뜻이며 API 응답에 나가지 않습니다.

- `20260825_0006_support_request_deal_link.sql`: 고객불만을 담당자 대신 고객사와 계약건에 맵니다.
  `support_request`에서 **`customer_contact_id`를 떼고** `customer_company_id`·`sales_deal_id`·
  `occurred_at`을 더합니다. 불만은 담당자 개인이 아니라 고객사가 산 물건에 대해 생기고,
  "어느 계약의 어느 제품인가"를 물어볼 데가 필요했습니다. 관련 제품과 워런티는 컬럼을 따로
  두지 않고 연결된 딜의 `product_id`·`warranty_terms`를 봅니다.
  회사와 딜은 각각 단일 외래키를 두지 않고 **복합 외래키 하나**
  (`(sales_deal_id, customer_company_id) → sales_deal(id, customer_company_id)`, `ON UPDATE CASCADE`)로
  묶어, 불만의 고객사가 그 딜의 고객사와 다를 수 없게 DB가 보장합니다. `sales_deal`이
  `sales_pipeline_stage`를 참조하는 방식과 같습니다. 참조 대상을 만들기 위해 `sales_deal(id,
  customer_company_id)`에 유일 제약 `sales_deal_id_customer_company_key`를 겁니다.
  `ON UPDATE CASCADE`를 안 걸면 불만이 붙은 딜은 고객사를 고칠 수 없게 막힙니다.
  `status_code`는 두 가지에서 네 가지(`received` 접수 / `diagnosing` 원인파악 /
  `in_progress` 처리중 / `completed` 처리완료)로 늘고, 지금까지 Pydantic 에만 있던 값 검사를
  DB의 CHECK 로도 겁니다. `occurred_at`은 접수자가 넣는 발생 시각이라 시스템이 찍는
  `registered_at`과 다르며 DEFAULT 를 두지 않습니다.
  기존 행은 어느 딜에 속하는지 알 근거가 없어 `support_response`와 함께 지우고 시작합니다.

- `20260826_0007_deal_quote_contract_order.sql`: 견적과 계약이 딜과 구분되어 자기 데이터를
  갖게 합니다. 지금까지 견적현황·계약현황은 `sales_deal`을 `phase_code`로만 거른 뷰였고, 세
  화면의 금액이 전부 `deal_amount` 하나를 읽어 견적가를 적으면 영업 예상금액이 덮였습니다.
  딜:견적:계약 = 1:1 이므로 표를 떼지 않고 `sales_deal`에 컬럼을 더합니다. **`deal_amount`는
  건드리지 않습니다** — 대시보드의 월매출·확정금액과 칸반 카드가 이미 읽고 있어 뜻을 바꾸면
  숫자가 조용히 달라집니다.
  `sales_deal` 28→33컬럼: `quote_status_id`, `contract_status_id`, `quote_amount`,
  `contract_amount`, `quote_delivery_terms`. 상태가 NULL 이면 아직 그 국면에 들어가지
  않았다는 뜻이고 견적현황·계약현황 목록이 이 조건(`has_quote`/`has_contract`)으로 갈립니다.
  `phase_code`로 거르면 계약으로 넘어간 딜이 견적번호를 들고 있는데도 견적현황에서 사라집니다.
  견적·계약 상태는 파이프라인 9단계와 다른 축이라 `purchase_order_status`와 같은 모양의
  팀별 룩업 `quote_status`·`contract_status`(각 10컬럼)를 새로 만듭니다.
  컬럼으로 표현할 수 없는 것만 표로 뗍니다. `sales_deal_item`(6컬럼, 견적 품목,
  `purchase_order_item`과 같은 모양. `quote_amount`는 이 줄들의 수량×단가 합)과
  `sales_deal_participant`(3컬럼, 미팅 대상자, `customer_contact_assignee`와 같은 모양)입니다.
  기존 `sales_deal.customer_contact_id`는 대표 담당자로 남습니다. 조회 스코프가 그 컬럼을 봅니다.
  `purchase_order` 13→17컬럼: `request_department`(기본 '영업팀')·`cooperation_department`
  (기본 '생산팀')·`created_by_member_id`·`expected_customer_company_id`. 뒤 둘은 NOT NULL 이며
  기존 발주는 걸린 딜의 `owner_member_id`·`customer_company_id`로 백필한 뒤 NOT NULL 을 겁니다.
  `purchase_order_status`는 라벨 하나만 고칩니다(`cancelled`의 이름 `취소` → `발주취소`).
  삭제·초기화는 없고 새 컬럼은 전부 NULL 허용이거나 기본값이 있어 적용 뒤에도 이전 백엔드가
  그대로 돕니다. **DB 적용이 백엔드 배포보다 먼저입니다.**

- `20260826_0008_contract_terms.sql`: 계약서 양식의 남은 두 항목에 자리를 만듭니다.
  `sales_deal` 33→35컬럼(`contract_payment_terms` 물품대금 지급기일,
  `contract_late_interest_terms` 대금연체 이자율). 둘 다 "납품 후 30일 이내",
  "상법 연이자 6%" 처럼 금액·날짜로 표현할 수 없는 문구라 `quote_delivery_terms`와 같은
  모양의 NULL 허용 text 입니다. 계약서 필수항목의 나머지는 컬럼을 더하지 않습니다 —
  계약자정보(갑)(을)은 딜의 고객사와 `team`의 회사명·사업자등록번호에서 유도하고,
  납품예상일자와 품목·수량·단가·금액은 딜:견적:계약이 1:1 이라 견적이 넣어 둔
  `quote_delivery_terms`·`sales_deal_item`이 같은 행에 그대로 있습니다. 보증기간은
  기존 `warranty_terms`입니다. 백필할 근거가 없어 기존 행은 NULL 이고 삭제도 없습니다.

- `20260826_0009_customer_company_address.sql`: `customer_company`에 `postcode`(5자리),
  `address`, `address_detail`을 더합니다. 고객 등록 화면이 다음(카카오) 우편번호 서비스로
  주소를 찾아 넣습니다. 주소는 사람이 아니라 회사에 붙는 값이라 `customer_contact`가 아니라
  여기에 둡니다. 회사 검색 목록도 같은 이름을 구분할 때 `business_no` 대신 이 주소를 먼저
  보여 줍니다. `postcode`·`address`는 우편번호 서비스가 주는 값이고 `address_detail`은
  층·호수처럼 사람이 직접 적는 부분입니다. 기존 행은 채울 근거가 없어 NULL로 둡니다.

- `20260827_0010_drop_activity_type.sql`: 활동에서 '업무'(task)를 없앱니다. 일정 등록 화면이
  단순해진 뒤 새 활동은 전부 미팅으로만 만들어지는데, 만들 수 없는 타입이 조회·집계에만 남아
  목록에는 옛 업무가 섞이고 미팅만 세는 카드와 전 타입을 세는 카드가 어긋났습니다.
  `activity`·`activity_category`·`activity_action_tag`에서 `activity_type`을 각각 떼어
  22→21 / 10→9 / 10→9컬럼이 되고, 인라인 CHECK도 컬럼과 함께 사라집니다.
  **삭제가 있습니다.** 업무 활동 전체와 그 카테고리(`internal` 내부업무), 액션태그 네 개
  (`weekly_review`·`monthly_review`·`quarterly_review`·`ojt`)를 지웁니다. 붙일 카테고리가
  사라지므로 업무 행을 남겨 둘 수 없습니다. `activity`를 가리키는 세 곳 중 cascade 는
  `activity_companion` 하나뿐이라 `report_activity` 행은 먼저 지우고
  `report.source_activity_id`는 NULL로 끊습니다. 보고서 자체는 지우지 않습니다.
  미팅 타입인 `internal_meeting`·`conference` 태그는 그대로 둡니다.
  **백엔드·프론트 배포가 DB 적용보다 먼저입니다** — 이전 코드는 INSERT에
  `activity_type`을 넣으므로 컬럼이 없으면 일정 등록이 깨집니다.

- `20260828_0013_report_sales_deal.sql`: 한 미팅에서 선택한 딜마다 보고서를 한 건씩 저장할 수
  있도록 `report.sales_deal_id`를 추가합니다. 기존 일정에 보고서와 단일 딜 연결이 각각 하나면
  이를 승계하고, 그 외 기존 보고서는 NULL을 유지합니다. 신규 미팅보고서는 API가 값을 필수로 받습니다.
  `(source_activity_id, sales_deal_id)` 부분 유일 인덱스로 같은 미팅·딜 보고서의 중복 생성을
  막고, 딜별 승인 보고서 조회용 인덱스를 둡니다.
- `20260829_0013_contract_next_meeting_suggestion.sql`: 캘린더 "AI 추천 일정" 패널이 조회하는
  `contract_next_meeting_suggestion`(7컬럼, RLS on)을 만듭니다. 딜 하나에 활성 제안은 하나라
  `sales_deal_id` 에 UNIQUE 를 겁니다. 날짜·사유 같은 내용은 복제하지 않고
  `schedule_management_run_id` 로 `agent_run.output_snapshot` 을 조회합니다.
  **개발 DB 에는 이 표가 이미 있습니다** — 아카이브한 브랜치
  (`archive/2026-08-28-contract-agent-fix`)를 시험하며 SQL 파일 없이 먼저 만든 것이라,
  컬럼·제약이 같은 것을 확인하고 `CREATE TABLE IF NOT EXISTS` 로 두었습니다.
- `20260831_0014_report_legacy_deal_scope.sql`: 보고서 0013의 백필 결과가 기존 본문의
  `sales_deal_ids`와 일치하지 않으면 `sales_deal_id`만 NULL로 되돌립니다. 여러 딜을 다룬
  통합보고서를 일정 대표 딜의 보고서로 오인하지 않기 위한 보정입니다. 본문과 선택 딜 목록,
  새 형식의 딜별 보고서는 보존합니다. **아직 DB에 적용하지 않았습니다.** 새 환경은 보고서
  0013 다음에 적용하고, 기존 환경은 대상 행 확인 후 별도 승인받아 적용합니다.

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
| 2026-08-24 | 개발 | `20260824_0004_product_fields.sql` | session pooler | 성공. product 4→9컬럼(`category_code`, `unit_price`, `shelf_life_months`, `memo`, `image_storage_key`). 기존 product 행이 0건이라 백필 대상 없음. `tests/test_models.py` 통과 |
| 2026-08-25 | 개발 | `20260825_0005_notice_management.sql` | session pooler | 성공. notice 12→18컬럼(`recipient_member_id` 제거, `type`·`display_start_date`·`display_end_date`·`is_hidden`·`sort_order`·`updated_at`·`deleted_at` 추가) / notice_target·notice_image 신설(RLS on) / `notice_team_recipient_published_idx` 를 `notice_team_type_order_idx`·`notice_visible_idx` 로 교체. 기존 notice 행이 0건이라 백필 대상 없음 |
| 2026-08-25 | 개발 | `20260825_0006_support_request_deal_link.sql` | session pooler | 성공. support_request 9→11컬럼(`customer_contact_id` 제거, `customer_company_id`·`sales_deal_id`·`occurred_at` 추가) / 복합 FK `support_request_sales_deal_company_membership_fkey`(ON UPDATE CASCADE)와 `sales_deal_id_customer_company_key` 신설 / `support_request_status_code_check` 를 값 목록 검사로 교체 / 인덱스 `support_request_sales_deal_company_idx`·`support_request_team_company_idx` 추가. support_request·support_response 행이 0건이라 삭제 대상 없음. 회사·딜 불일치 INSERT 와 없는 상태값 INSERT 가 각각 FK·CHECK 로 거절되는 것까지 확인 |
| 2026-08-26 | 개발 | `20260826_0007_deal_quote_contract_order.sql` | session pooler | 성공. quote_status·contract_status(각 10컬럼)·sales_deal_item(6컬럼)·sales_deal_participant(3컬럼) 신설(RLS on) / sales_deal 28→33컬럼 / purchase_order 13→17컬럼. 기존 발주 9건 모두 걸린 딜의 owner_member_id·customer_company_id 로 백필한 뒤 NOT NULL 적용(NULL 0건). 부서 두 칸은 DEFAULT 대로 '영업팀'/'생산팀'. purchase_order_status 의 `cancelled` 라벨 2행을 '취소'→'발주취소' 로 변경. 기존 딜 52건의 신규 컬럼은 전부 NULL(아직 견적·계약 없음). `tests/test_models.py` 의 신규 4표·컬럼 수 대조 통과 |
| 2026-08-26 | 개발 | `20260826_0008_contract_terms.sql` | session pooler | 성공. sales_deal 33→35컬럼(`contract_payment_terms`·`contract_late_interest_terms`). 둘 다 NULL 허용이라 기존 딜 52건은 NULL 그대로이고 백필 대상이 없습니다. `tests/test_models.py` 의 물리 스키마 대조 통과 |
| 2026-08-26 | 개발 | `20260826_0009_customer_company_address.sql` | session pooler | 성공. customer_company 6→9컬럼(`postcode`·`address`·`address_detail`, 전부 nullable). 기존 36행은 백필 없이 NULL. `tests/test_models.py` 의 컬럼 수 대조 통과 |
| 2026-08-28 | 개발 | `20260828_0013_report_sales_deal.sql` | session pooler | 성공. report +1컬럼(`sales_deal_id`, nullable) / 부분 유일 인덱스·딜별 날짜 인덱스 추가. 기존 report 128행 보존(128→128) |
| 2026-08-28 | 개발 | `20260827_0010_drop_activity_type.sql` | session pooler | 성공. activity 22→21 / activity_category 10→9 / activity_action_tag 10→9컬럼. 업무 활동 28건(전부 미삭제 상태)과 그 report_activity 3건을 지우고 report 1건의 `source_activity_id` 를 NULL 로 끊었다. 딸린 activity_companion 은 0건. 액션태그 8행·카테고리 2행 삭제(팀 2개 × 4/1). 미팅 활동 377건과 report 229건은 그대로. ORM 대조에서 세 표의 컬럼·nullable·타입·기본값·PK·FK 일치 확인 |
| 2026-08-28 | 개발 | `20260828_0011_sales_deal_source.sql` | — | **적용 시점 미상.** 0010 을 넣기 전 확인해 보니 `sales_deal.source_code` 와 `sales_deal_source_code_check` 가 이미 있었고 값이 든 딜이 122건이었다. 저장소 밖에서 먼저 적용된 것으로 보이며 이 줄은 사후 기록이다 |
| 2026-08-28 | 개발 | `20260828_0012_document_product_link.sql` | — | **적용 시점 미상.** 위와 같이 `document.product_id`·`document_product_id_fkey`·`document_product_idx` 가 이미 있었다. 사후 기록이다 |

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
    public.notice_image,
    public.notice_target,
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

> **팀별 룩업은 팀마다 따로 넣어야 합니다 (2026-08-26).** 이 스크립트는 데모 팀
> (`6d0f1b76…`) 하나만 봅니다. `20260826_0007`로 생긴 `quote_status`·`contract_status`도
> 마찬가지라, 다른 팀 계정으로 로그인하면 견적현황·계약현황 탭이 비고 작성 폼의 저장이
> 잠깁니다(`statuses.length === 0`). 개발 DB의 `테스트1`(`a71b1b30…`)은 딜 41건·발주 9건을
> 들고 있어 같은 날 두 표에 5행씩을 따로 넣었습니다. ID는 이 스크립트와 같은
> `configuration_id(team_id, table_name, code)` 규칙을 써서 나중에 seed를 그 팀에 돌려도
> 중복되지 않습니다. `seed_team_configuration`을 통째로 다른 팀에 돌리지는 않았습니다 —
> 그 팀은 이미 자기 파이프라인으로 딜을 굴리고 있어 파이프라인·단계까지 건드리게 됩니다.

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
