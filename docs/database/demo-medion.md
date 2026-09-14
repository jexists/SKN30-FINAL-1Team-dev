# 메디온 데모 데이터

팀 **파이널**(회사명 `메디온솔루션 영업1팀`)에 로그인해 화면을 돌아다녔을 때 실제 업무처럼
이어진 데이터가 보이도록, 반복 실행 가능한 데모 데이터를 넣는다.

기존 [`scripts/seed_sample_bracelet.py`](../../backend/scripts/seed_sample_bracelet.py) 는 팀
`테스트1` 에 기준일이 `2026-08-25` 로 하드코딩된 서사를 넣는다. 이 문서의 시더는 별개이며
다른 팀에 규칙으로 생성한 데이터를 넣는다. 서로 건드리지 않는다.

## 1. 실행

```bash
cd backend

# 엑셀 파서 자체 검사 (DB 불필요)
uv run python -m scripts.demo.hospitals

# DB 없이 시더 로직만 검사한다. 시더를 고쳤으면 여기부터 돌린다.
uv run python -m scripts.demo.check_offline
uv run python -m scripts.demo.check_offline 2026-12-25   # 기준일을 바꿔도 되는지

# 저장하지 않고 결과만 본다
uv run python -m scripts.seed_demo_medion --dry-run

# 기본 동작: reset → seed → verify
uv run python -m scripts.seed_demo_medion

# 부분 실행
uv run python -m scripts.seed_demo_medion --reset
uv run python -m scripts.seed_demo_medion --seed
uv run python -m scripts.seed_demo_medion --verify

# 검증만 따로 (읽기 전용)
uv run python -m scripts.verify_demo_medion
```

| 옵션 | 뜻 |
|---|---|
| `--base-date` | 기준일. 기본값은 실행일이다. 바꿀 때는 `--reset` 이 함께 필요하다 |
| `--reset` | 이 팀의 업무 데이터를 지운다 |
| `--seed` | 데이터를 넣는다 |
| `--verify` | 검증만 돌린다 |
| `--dry-run` | 트랜잭션을 되돌린다 |
| `--yes` | 확인 입력을 건너뛴다 |

아무 단계도 고르지 않으면 `reset → seed → verify` 를 모두 한다. `seed` 는 끝에서 검증을
자동으로 돌리고, 한 건이라도 실패하면 종료 코드 1 로 끝난다.

`APP_ENV=production` 이면 실행되지 않는다. 실행 전에 연결 대상 호스트와 팀 이름, 두 계정을
출력하고, 대화형 터미널에서 `--reset` 을 쓰면 팀 이름을 그대로 입력받아 확인한다.

### 환경변수

`DATABASE_URL` 과 `APP_ENV` 만 있으면 된다.

**비밀번호를 받지 않는다.** 시더가 계정을 만들지 않기 때문이다. Supabase Auth 를 전혀 부르지
않으므로 `SUPABASE_SECRET_KEY` 도 필요 없다.

## 2. 팀과 계정

팀과 계정은 **사람이 이미 만들어 둔 것을 쓴다.** 시더는 조회만 하고 만들지도 고치지도 않는다.
팀 이름, 회사명, 구성원의 표시 이름·역할·배지색을 건드리지 않는다.

| 이메일 | 이름 | 권한 |
|---|---|---|
| `medion.leader@gmail.com` | 노재현 | manager |
| `medion.member@naver.com` | 박지훈 | member |

팀 `파이널` (`d7a261eb-ad8d-4805-ab93-1c8a11830e44`) 에는 이 둘 말고
`medion.member1~3@naver.com` 세 명이 더 있다. **데모 데이터는 위 두 계정에만 붙는다.**
나머지 세 명은 팀 관리 화면에 실적 0 으로 남는다.

기대와 다르면(계정이 없거나, 다른 팀이거나, 역할·이름이 다르면) 엉뚱한 곳에 쓰지 않으려고
바로 중단한다. 계정은 Supabase Dashboard 와 `/admin` 화면에서 발급한다.

## 3. 생성 규모

기준일 2026-09-15 기준.

| 테이블 | 건수 | 비고 |
|---|---|---|
| `product` | 11 | Sales_DB.xlsx 품목리스트의 LR/LP 모델과 판매단가 |
| `customer_company` | 400 | 공공데이터 영업중 병원에서 17개 시도 고르게 추출 |
| `customer_contact` (+`_assignee`) | 120 | 앞쪽 100개 고객사에만. 20건은 팀장·팀원 공동 배정. 100건에 영업 메모, 20건은 빈 메모 |
| `sales_deal` (+`_item`) | 130 (260) | 9단계 전부. 확정 119 · 진행중 9 · 취소 2 |
| `purchase_order` (+`_item`) | 20 (20) | 납품 완료 18 · 진행 중 2 |
| `activity` | 372 | 서사 흐름 109 + 평일 채움 238 · 오늘 6 · 미래 19 (완료 0) |
| `report` (+`report_deal`) | 504 (404) | 미팅 328 · 일일 140 · 주간 30 · 월간 6. 미팅 76건은 딜 2건 |
| `support_request` (+`_response`) | 8 (9) | 접수·원인파악·처리중·처리완료 각 2 |
| `notice` (+`notice_target`) | 6 (3) | 공지 3 + 팀장 지시사항 3 |
| `sales_target` | 25 | 2명 × 13개월. 과거 한 달은 일부러 비움 |

고객사 400곳 중 영업활동이 붙는 곳은 100곳이다. 나머지 300곳은 담당자와 딜이 없는 미개척
고객사로 남아 고객 목록의 검색·지역 필터·페이지네이션(30건/쪽)을 시험할 수 있게 한다.

## 4. 날짜

모든 날짜가 기준일의 상대 오프셋이다. 스크립트에 절대 날짜 리터럴이 없다.

```text
(기준연도−2)-01 ─── 매출용 얕은 딜 ───┃ base−150 ── 서사 구간 ── base ── base+45
                    계약·금액만        ┃ 활동/보고서/발주/CS      오늘   예정
                                      ┃ 보고서 작성 완료         미작성  보고서 0건
```

- **매출 구간**: 2년 전 1월부터 이번 달까지 매월 계약이 체결된 확정 딜을 깔아 둔다.
  기준일이 2026-09-14 면 2024-01 ~ 2026-09 **33개월**이 채워진다. 이 구간의 옛 딜은
  딜과 품목만 갖고 활동·보고서는 없다.
- **서사 구간**: 활동·보고서·발주·C/S 가 붙는 딜 17건. 파이프라인 9단계를 모두 채운다.
- **평일 채움**: 서사 딜의 FLOW 만 따르면 미팅이 하루도 없는 평일이 대부분이라 화면이 빈다.
  기준일 −14 ~ +3(이번 달 구간)은 **평일마다 1인당 3건**, 그 이전 7개월은 **평일 열에 여덟만
  1인당 1건**을 채운다(`DENSE_*`, `SPARSE_*`). 채움 미팅은 그 날 살아 있던 딜 — 서사 딜뿐
  아니라 매출 축의 얕은 딜도 — 에 붙고, 개설일로부터 지난 날수에 가장 가까운 FLOW 단계를 써
  제목과 보고서 본문이 딜 진행과 어긋나지 않게 한다.
- **일일·주간 보고서는 월간이 덮는 구간과 같은 날부터 만든다**(`PERIOD_MONTHS`). 보고서 상세의
  '관련 보고서' 는 하위 보고서를 날짜로 다시 조회해 그리므로(5절), 구간이 짧으면 월간을 열었을 때
  관련 보고서가 빈다.
- **한 주가 지난 보고서는 확정(approved)** 이다. 열에 한 건만 검토 대기로 남긴다. 3~7일 전은
  검토 대기, 3일 안쪽은 작성중이다. 한 달 전 보고서가 검토 대기로 남으면 결재가 멈춘 팀처럼 보인다.
- **지난 일정은 하나도 빠짐없이 미팅 보고서를 갖는다.** 화면이 완료된 미팅에
  '보고서 미작성' 을 띄우므로 일부 단계만 채우면 데모 중에 빈 칸이 그대로 드러난다.
- **미래 일정에는 보고서가 없다.** **오늘 일정은 완료 처리되지 않고 보고서도 없다.**
  아직 일어나지 않은 미팅이다. 셋 다 검증이 확인한다.
- 견적 유효기간, 계약 종료일, 진행 중 발주의 입고 예정일만 미래 날짜를 가진다.

`--base-date` 를 바꿀 때 `--reset` 을 요구하는 이유는, 날짜 축만 옮기면 계약일과 발주일,
보고서 상태가 서로 어긋나기 때문이다. 기준일 변경은 전체 재생성이다.

## 5. 데이터 연결

실제 외래키만 쓴다. ERD 에 없는 관계는 만들지 않았다.

```text
customer_company ── customer_contact ── customer_contact_assignee ── member
      │
      └── sales_deal ──┬── (견적: quote_no / quote_issued_on / quote_valid_until / quote_amount)
           │           ├── (계약: contract_no / contract_signed_on / contract_ends_on)
           │           ├── sales_deal_item ── product
           │           ├── purchase_order ── purchase_order_item ── product
           │           ├── support_request ── support_response
           │           └── activity ──┬── report (미팅, source_activity_id) ── report_deal
           │                          └── report_activity ── report (일일·주간·월간)
           └── sales_target (담당자 × 월)
```

### 지시사항 → 업무 → 보고서

`notice` 에서 `activity` 나 `report` 로 가는 외래키가 **스키마에 없다.**
`activity.note` 첫 줄에 `지시사항: {제목} (기한 M월 D일)` 을 적어 화면에서 근거가 보이게 했다.

```text
notice(DIRECTIVE) ──[notice_target: FK]──> member
                                            │  ← FK 없음. 날짜·담당자·본문 인용으로만 연결
                                            ▼
                                         activity
                                            │  ← report.source_activity_id: FK
                                            ▼
                                          report ──[reviewed_by_member_id: FK]──> 팀장 확인
```

세 지시사항의 이행 상태를 `done` · `pending` · `not_done`(사유 포함)으로 나눠 공지 관리
화면의 이행 현황 칸을 시연한다. **지시사항은 `notice_target` 이 없으면 팀장에게도 팀원에게도
보이지 않는다.**

## 6. 화면이 비지 않게 하는 규칙

시더가 지키는 제약이다. 고칠 때 같이 봐야 한다.

| 규칙 | 근거 |
|---|---|
| 매출 = 확정 단계 딜의 `contract_amount` 합, `contract_signed_on` 의 월로 버킷 | [`dashboard.py`](../../backend/app/api/dashboard.py) `_sales_target_card`. 대시보드·`/team`·매출분석이 같은 규칙이다. **`deal_amount` 는 어느 매출 경로에서도 합산되지 않는다** |
| `sales_target` 은 `customer_company_id IS NULL` 행만 | 대시보드는 전부 합산하지만 `/team` 은 NULL 행만 합산한다. 섞으면 두 화면이 다른 숫자를 말한다 |
| 발주가 붙은 딜은 `order_in_progress` / `order_delivered` 단계 | [`orders.py`](../../backend/app/api/orders.py) 의 목록 API 가 `phase_code = 'order'` 를 강제한다 |
| 활동의 `customer_company_id` = 딜의 `customer_company_id` | 어긋나면 모든 활동 조회에서 조용히 사라진다 |
| 활동 담당자 = 고객 담당자의 소유자 | 팀원 역할은 '내 활동이면서 내 고객' 만 본다. 어긋나면 그 팀원 화면에서 일정이 통째로 사라진다 |
| `notice.display_start_date <= 오늘`, `is_hidden = false` | 아니면 대시보드 티커에 뜨지 않는다 |
| C/S 는 계약 이후(`contract`·`order`·`closed`) 딜에만 | `support_request` 가 `(sales_deal_id, customer_company_id)` 복합 FK 라 짝이 맞아야 한다 |
| 보고서 상세의 '관련 보고서' 는 링크 테이블이 아니라 **하위 보고서를 날짜로 다시 조회**해 그린다 | `Daily/Detail.tsx` → `useDailyReports.ts` `childReportQuery()` → `sources.ts` `rollupSources`. 월간은 그 달의 `weekly`, 주간은 그 주의 `daily` 를 `status_code ∈ {submitted, approved}` 로 찾는다. 하위 보고서를 그 구간에 만들어 두지 않으면 패널이 빈다 (`report_source` 를 채워도 화면은 읽지 않는다) |
| 고객현황 메모는 상태 코드에 맞는 문장만 쓴다 | `CONTACT_MEMOS`. 120건 중 20건은 비워 '등록된 메모가 없습니다' 빈 화면도 시연한다 |
| 지난 일정마다 `report(report_kind='meeting')` 한 건 | 완료된 미팅에 보고서가 없으면 일정 상세에 '보고서 미작성' 이 뜬다 |
| 미팅 정보(부서·담당자·장소)는 `report.content` 에만 있다 | 화면이 여기만 읽는다(`useMeetingReports.ts`). 비우면 영영 `—` 다 — 일정을 다시 조회하는 경로가 없다 |
| 본문은 `**소제목**` 한 줄 + 빈 줄 + 문단 | `reportSections.ts` 의 `/^\*\*(.+?)\*\*$/` 가 구획을 찾는다. 없으면 줄글로 그린다 |
| 미팅 공통·미지정 기록은 소제목 없는 `- ` 목록 | `report-shared/SKILL.md`. 여기에 소제목을 쓰면 실제 에이전트 출력과 달라진다 |
| 후속 조치 이름표는 `FIELD_LABELS` 안의 것만 | 구분자는 앞뒤 공백이 있는 ` · `. 벗어나면 카드로 안 그려진다 |
| 보고서 양식 id 는 `builtin-*-freeform` | `frontend/src/shared/meetings.ts`, `reports.ts` 와 같아야 한다 |

## 7. 원본 데이터

### `data/sample/hospital_list_공공데이터_v2.xlsx`

8,306행 14컬럼 중 `business_status = '영업중'` 인 3,440행에서 지역이 고르게 섞이도록 400곳을
고른다. `customer_company` 에 자리가 있는 컬럼은 **넷뿐**이다.

| 엑셀 컬럼 | → | 변환 |
|---|---|---|
| `hospital_name` | `name` | 중복은 `병원명 (시·군·구)` 로 보정. `(team_id, name)` 이 유일 |
| `postal_code` | `postcode` | `3136.0` → `03136`. 5자리를 못 만들면 `NULL` (98% 성공) |
| `road_address` / `lot_address` | `address` | 도로명 우선, 없으면 지번 |
| 주소 첫 토큰 | `region_code` | 광역시도 → 프론트의 영문 코드(`seoul`·`gyeonggi`…) |

`region_code` 를 한글 이름 그대로 넣으면 `regionLabel` 이 코드를 날것으로 보여주고 지역
선택란과 매출분석 지역별 집계가 그 값을 못 고른다. 그래서
[`regionCodes.ts`](../../frontend/src/shared/regionCodes.ts) 의 17개 코드로 옮긴다.
원본이 광주광역시와 전라남도를 `전남광주통합특별시` 하나로 합쳐 두어(1,347건), 둘째 토큰이
광주 5개 자치구면 `gwangju`, 아니면 `jeonnam` 으로 되돌린다.

나머지 10개 컬럼(`hospital_phone` · `business_type` · `hospital_type` · `business_status` ·
`medical_staff_count` · `inpatient_room_count` · `specialties` · `source_x` · `source_y` ·
`source_updated_at`)은 **대응 컬럼이 없어 버린다.** 좌표는
[`AGENTS.md`](../../AGENTS.md) 의 위치 메타데이터 규칙 대상이기도 하다.

`business_no` 는 원본에 없다. 지어내면 실존 사업자와 겹칠 수 있어 전부 `NULL` 로 둔다.

### 제품

[`data/sample/Sales_DB.xlsx`](../../data/sample/Sales_DB.xlsx) 품목리스트 시트의 11개
모델(LR/LP 체계와 판매단가)을 그대로 쓴다. `product.category_code` 는 CHECK 상
`system` / `probe` / `consumable` 셋뿐이라 제품군을 여기에 맞춘다.

`★MEDICAL_DEVICE_PRICE_LIST_2020.7.15기준_게시용_데모.xlsx` 는 **쓰지 않는다.** 제품
카탈로그가 아니라 심평원 치료재료 급여목록(23시트, 4만여 행)이라 레이저장비 대리점의
`product` 에 넣으면 데이터가 앞뒤로 맞지 않는다.

### 사람과 연락처

병원 이름과 주소만 공공데이터 원본이다. 담당자 이름·부서·직급·연락처·이메일은 전부 가상이며
[`data-sanitization-rules.md`](../data-sanitization-rules.md) 에 따라 통화되지 않는
`010-0000-NNNN` 형식과 예약 도메인 `.test` 를 쓴다.

## 8. 리셋 범위

### 지우는 것

팀 `파이널` 이 소유한 **업무 데이터만**. 삭제는 생성의 역순이다.

```text
report_attachment(report_id IS NULL) → file(부모가 팀 report/document) → document
→ contract_next_meeting_suggestion(팀 딜) → report_submission → report
   [report_source · report_activity · report_deal · meeting_deal_analysis 는 CASCADE]
→ agent_run → sales_target(두 데모 계정만) → notice_image → notice [notice_target CASCADE]
→ support_request_edit_backup → support_response → support_request
→ activity [activity_companion CASCADE]
→ purchase_order [purchase_order_item CASCADE]
→ sales_deal [sales_deal_item · sales_deal_participant CASCADE]
→ customer_contact(팀 고객사 소속) [customer_contact_assignee CASCADE]
→ customer_company → product
```

### 지우지 않는 것

- **`team` 과 `member`, Supabase Auth 사용자** — 사람이 만든 고정 자산이다
- **`medion.member1~3@naver.com` 세 명의 `sales_target`** — `sales_target` 의 삭제 범위는
  팀 전체가 아니라 두 데모 계정으로 좁혀 두었다
- **팀별 룩업 7종**(`customer_contact_status` · `activity_category` · `activity_action_tag` ·
  `sales_deal_type` · `quote_status` · `contract_status` · `purchase_order_status`)과
  `sales_pipeline`(+`_stage`) — 지우면 남은 행이 참조할 대상이 사라진다

**다른 팀·다른 계정의 행은 어떤 경로로도 삭제 대상에 들어가지 않는다.** 모든 삭제 조건이
`team_id = TEAM_ID` 이거나 이 팀이 소유한 부모의 서브쿼리다.

## 9. 재실행

모든 행의 id 가 `uuid5(team_id, "medion2026:{종류}:{자연키}")` 라 다시 실행해도 같은 행을
갱신할 뿐 늘어나지 않는다. 기준일은 키에 넣지 않는다 — 넣으면 날짜가 바뀔 때마다 새 행이
쌓인다. 난수도 `random` 이 아니라 키의 blake2b 해시에서 뽑는다. `random.seed()` 는 파이썬
판이 바뀌면 수열이 달라져, 같은 기준일로 다시 돌렸을 때 데이터가 조용히 바뀐다.

## 10. 검증

`scripts.verify_demo_medion` 이 **63개 검사**를 돌린다. 수량은 상수와 원본 엑셀에서 직접
뽑으므로 숫자를 두 곳에 적어 두지 않는다. 검사에 더해 표별 행 수, 단계별 딜, 연도별·최근
6개월 확정 매출, 담당자별 목표 대비 실적, 보고서 종류·상태, 일정 구간, C/S 상태, 지시사항
이행 현황을 표로 찍는다.

- **계정·팀** — 두 데모 계정이 이 팀에서 활성, 활성 팀장 1명, `member` 가 `auth.users` 에 있음
- **대시보드** — 오늘 일정이 두 사람 모두에게, 이번 달 목표·확정 매출이 두 사람 모두에게,
  계약 갱신 예정 ≥ 1, 발주 목록에 보이는 발주 ≥ 10
- **보고서** — 보고서가 없는 지난 일정 0, 미팅 보고서에 근거 일정·딜 섹션 누락 0,
  미래 일정에 보고서 0, 오늘 일정에 확정 보고서 0, 검토 대기 ≥ 1, 팀장 검토 완료 ≥ 1,
  반려 ≥ 1, 종류 4가지
- **서식** — 미팅 정보가 빈 보고서 0, 소제목 없는 본문 0, 공통 기록에 소제목 섞임 0,
  ML 근거 없는 딜 섹션 0, 한 미팅에 고객사 다른 딜 0, 딜 2건 미팅 ≥ 1, 공통 기록 ≥ 1
- **팀 격리·참조 무결성** — 팀 밖 참조 0, 활동/C/S 의 고객사가 딜과 다름 0, 활동 담당자와
  고객 담당자 불일치 0, 담당 배정 없는 고객 담당자 0
- **날짜·값·중복** — 개설 ≤ 견적 ≤ 계약 위반 0, 계약일보다 앞선 발주 0, 발주 합계 >
  계약금액 0, 확정인데 계약일 없음 0, 미래 계약 0, 고객사 이름·딜/견적/계약/발주 번호 중복 0
- **2년 매출** — 확정 매출이 잡히는 달 ≥ 24, 연도 ≥ 3, 목표를 넘긴 담당자·월 ≥ 1,
  회사별 목표 행 0

DB 없이 도는 `scripts.demo.check_offline` 은 같은 불변식을 순수 파이썬으로 확인한다. 개발과
운영이 같은 DB 를 쓰고 있으므로, 시더를 고친 뒤에는 이쪽을 먼저 돌려 공유 DB 를 건드리지 않고
거른다. 기준일을 여러 개 돌려 구조가 유지되는 것도 함께 본다.

## 11. 구성 파일

| 파일 | 역할 |
|---|---|
| [`scripts/seed_demo_medion.py`](../../backend/scripts/seed_demo_medion.py) | 진입점, `Seeder`, `reset_demo_data` |
| [`scripts/verify_demo_medion.py`](../../backend/scripts/verify_demo_medion.py) | 읽기 전용 검증 |
| [`scripts/demo/medion.py`](../../backend/scripts/demo/medion.py) | 상수 (팀·구성원·제품·공지·지시·C/S·서사 딜) |
| [`scripts/demo/hospitals.py`](../../backend/scripts/demo/hospitals.py) | 엑셀 → 고객사 정규화 |
| [`scripts/demo/_xlsx.py`](../../backend/scripts/demo/_xlsx.py) | 표준 라이브러리만으로 .xlsx 읽기 |
| [`scripts/demo/check_offline.py`](../../backend/scripts/demo/check_offline.py) | DB 없이 도는 검사 |

`_xlsx.py` 를 손으로 쓴 이유는 의존성을 늘리지 않기 위해서다. 시더가 엑셀을 한 번 읽는 것이
전부인데 그 때문에 `openpyxl` 을 모든 배포에 얹을 이유가 없다. `.xlsx` 는 XML 을 담은 zip 이라
`zipfile` 로 충분하다.

`hospitals.py` 와 `check_offline.py` 는 `python -m` 으로 직접 실행하면 자체 검사를 돈다.

## 12. 보고서 서식

실제 AI 보고서와 같은 꼴로 쓴다. 화면이 본문을 구획으로 읽기 때문이다.

유형별 고정 항목은 `backend/app/agents/reports/skills/*/SKILL.md` 의 `작성 순서` 를 따른다.

| 유형 | 소제목 | 마지막 항목 |
|---|---|---|
| 미팅(딜별) | 미팅 목적 → 논의 내용 → 고객 요구 → 합의사항 → 후속 조치 | 목록 |
| 일일 | 오늘 한 일 → 거래처별 결과 → 미완료·문제 → 다음 업무 | 목록 |
| 주간 | 목표 → 실적 → 차이 → 원인 → 다음 주 조치 | 목록 |
| 월간 | 성과 → 원인 → 문제 → 개선안 → 다음 달 계획 | 목록 |

```text
**미팅 목적**
                    ← 빈 줄이 있어야 문단으로 읽힌다
{company} 구매부서와 견적 구성을 협의했습니다.

…

**후속 조치**

- **견적 회신 팔로업 연락** · 담당: 본인 · 기한: 9월 21일 · 완료 기준: 회신 확보 · 상태: 요청
```

근거가 없는 항목은 `해당사항 없음 (제공된 자료에 관련 내용 없음)` 으로 둔다. `ReportView` 가
이 말로 시작하는 값을 회색으로 뺀다. 모든 칸을 자신 있게 채우면 오히려 사람이 쓴 요약처럼
보인다.

### 한글 조사

템플릿에 조사를 박아 두면 `이화병원와`, `박지우 대리이` 같은 비문이 나온다. `josa()` 가 받침
유무로 골라 붙인 자리표시자(`person_sub` · `person_nom` · `person_with` · `company_with`)만
쓴다. `check_offline` 이 템플릿에 `{자리표시자}조사` 가 남아 있는지 **원인 자리에서** 검사한다.

### 딜 2건짜리 미팅

같은 고객사·같은 담당자의 다른 딜이 있고 그 딜이 미팅일 이전에 열렸으면, 세 번에 한 번꼴로
한 미팅에 묶는다. 새 딜을 만들지 않는다. 이때만 `report.common_body` 에 공통 기록을 남기고,
일부에는 `unassigned_body` 도 채워 `딜 미지정 · 확인 필요` 블록을 시연한다.

### ML 배지

`report_deal.ai_evidence.deal_assessment` 가 딜 카드의 배지를 만든다. 단계로 확률을 정한다 —
계약·발주는 `high` 0.78~0.93, 견적·계약서 발송은 0.55~0.75, 초기 단계는 `watch` 0.30~0.50,
취소는 0.15~0.30.

**실제 모델을 돌린 값이 아니다.** `model_version` 을 `demo-seed-v1` 로 둬 그 사실이 데이터에
남게 했다. `agent_run` 행은 만들지 않는다 — 실제 AI 실행 로그라 손으로 넣으면 감사 기록이
오염된다.

## 13. 알려진 제약

- **자료실(`document`·`file`)과 AI 실행 로그(`agent_run`)는 만들지 않는다.** 자료실은
  Supabase Storage 업로드가 필요하고, `agent_run` 은 실제 AI 실행 로그라 손으로 넣으면 감사
  기록이 오염된다. 필요하면 에이전트를 실제로 한 번 돌린다. reset 은 둘 다 지울 수 있게 짜
  두었다.
- **보고서에 귀속된 `report_attachment` 가 생기면 reset 이 막힌다.**
  `report_attachment_immutable` 트리거가 `report_id IS NOT NULL` 인 행의 DELETE 와 UPDATE 를
  모두 거부한다([`20260907_0024`](../../backend/sql/20260907_0024_report_attachment_originals.sql)).
  시더는 첨부를 만들지 않지만, 데모 중 사람이 올리면 그 뒤 reset 은 해당 id 를 찍고 중단한다.
  되살리려면 DBA 가 트리거를 우회해야 한다.
- **개발과 운영이 같은 DB 다**([`sql/README.md`](../../backend/sql/README.md)). 데모 팀 밖은
  건드리지 않지만 쓰기는 되돌릴 수 없다.
- **`/notifications` 화면은 클라이언트 로컬 스토어**라 시딩으로 채울 수 없다.
- **`AI 작성` 배지는 시딩할 수 없다.** React 세션 상태다(`useMeetingDraft.ts`). 실제 AI
  보고서도 저장한 뒤 다시 열면 이 배지가 사라진다.
- **`미팅 원문 파일` · `참고자료` 는 `첨부 없음` 으로 남는다.** `report_attachment` 는
  Storage 업로드가 필요하고, 보고서에 귀속되면 아래 트리거가 reset 을 영구히 막는다.
- **팀 이름이 `파이널` 이다.** 의료기기 영업팀임이 팀 이름만으로는 드러나지 않는다. 회사명이
  `메디온솔루션 영업1팀` 이라 화면에서는 맥락이 보인다. 팀 이름을 바꾸려면 팀 관리 화면에서
  직접 바꾼다 — 시더는 사람이 정한 이름을 건드리지 않는다.
