# 데모 데이터셋

로그인해서 화면을 돌아다녔을 때 실제 업무처럼 이어진 데이터가 보이도록, 데모 팀 하나에
반복 실행 가능한 샘플 데이터를 넣는다.

기존 [`scripts/seed_sample_bracelet.py`](../../backend/scripts/seed_sample_bracelet.py) 는
팀 `테스트1` 에 손으로 쓴 서사를 넣고 기준일이 `2026-08-25` 로 하드코딩되어 있다. 이 문서의
시더는 별개이며 다른 팀에 규칙으로 생성한 데이터를 넣는다. 서로 건드리지 않는다.

## 1. 실행

```bash
cd backend

# 계정 생성에 쓸 비밀번호. 앞에 공백 한 칸을 두면 셸 히스토리에 남지 않는다.
 export DEMO_SEED_PASSWORD='...'

# DB 없이 논리만 검사한다. 시더를 고쳤으면 여기부터 돌린다.
uv run python -m scripts.demo.check_offline
uv run python -m scripts.demo.check_offline 2026-12-25   # 기준일을 바꿔도 되는지

# 저장하지 않고 결과만 본다. 계정과 파일은 만들지 않는다.
uv run python -m scripts.seed_demo_dataset --dry-run

# 최초 생성 (실행일 기준). 계정이 없으면 여기서 만든다.
uv run python -m scripts.seed_demo_dataset

# 테스트 → 문제 발견 → 초기화 → 재테스트
uv run python -m scripts.seed_demo_dataset --reset

# 발표·스크린샷용으로 날짜를 고정해 재현
uv run python -m scripts.seed_demo_dataset --reset --base-date 2026-08-31

# 검증만 따로 (읽기 전용)
uv run python -m scripts.verify_demo_dataset
```

`seed` 는 끝에서 검증을 자동으로 돌리고, 한 건이라도 실패하면 종료 코드 1 로 끝난다.

| 옵션 | 뜻 |
|---|---|
| `--base-date` | 기준일. 기본값은 실행일이다. 바꿀 때는 `--reset` 이 함께 필요하다 |
| `--reset` | 이 시더가 만든 행만 지우고 다시 만든다 |
| `--dry-run` | 트랜잭션을 되돌린다. 계정 생성과 파일 업로드는 건너뛴다 |
| `--skip-documents` | 자료실과 Storage 업로드를 건너뛴다 |
| `--yes` | `--reset` 확인 프롬프트를 건너뛴다 |

`APP_ENV=production` 이면 실행되지 않는다. 계정 생성에 쓰는
`supabase_auth.create_confirmed_user()` 가 로컬 전용이기 때문이다.

## 2. 계정

이메일은 고정이라 실행할 때마다 새 사용자가 생기지 않는다. 이미 있으면 조회해 재사용한다.
`example.com` 은 RFC 2606 예약 도메인이라 실제로 메일이 나가지 않는다.

| 이메일 | 이름 | 권한 |
|---|---|---|
| `demo.manager@example.com` | 한지현 | manager |
| `demo.sales1@example.com` | 서민우 | member |
| `demo.sales2@example.com` | 오재훈 | member |
| `demo.sales3@example.com` | 배수연 | member |
| `demo.sales4@example.com` | 노가람 | member |

비밀번호는 `DEMO_SEED_PASSWORD` 환경변수로만 받는다. 코드·로그·문서에 남기지 않는다.
팀장은 `member_one_manager_per_team_uq` 때문에 팀당 한 명이다.

`--reset` 은 계정과 팀, 팀별 설정 룩업, 파이프라인을 지우지 않는다. 계정은 고정 자산이고,
룩업을 지우면 남은 행이 참조하는 대상이 사라진다.

## 3. 생성 규모

| 테이블 | 건수 | 비고 |
|---|---|---|
| `team` / `member` | 1 / 5 | 팀장 1 + 담당자 4 |
| `product` | 50 | system 12 · probe 14 · consumable 24 |
| `customer_company` | 3,440 | 공공데이터 영업중 병원 전량 |
| `customer_contact` (+ `_assignee`) | 약 700 | 앞쪽 520개 고객사에만 |
| `sales_deal` (+ `_item`) | 220 (약 330) | 9단계 전부 채움 |
| `purchase_order` (+ `_item`) | 60 (60) | 계약 서명이 끝난 딜에만 |
| `activity` | 약 1,510 | 과거 1,220 · 오늘 20 · 미래 269 |
| `report` (+ `report_activity`) | 약 426 | meeting 210 · daily 164 · weekly 40 · monthly 12 |
| `support_request` (+ `_response`) | 60 (78) | 접수 14 · 원인파악 11 · 처리중 15 · 완료 20 |
| `notice` (+ `notice_target`) | 20 (28) | NOTICE 10 + DIRECTIVE 10 |
| `sales_target` | 약 27 | 5명 × 6개월, 일부는 일부러 비움 |
| `document` (+ `file`) | 12 (12) | 실제 공개자료 요약 + `.docx` 첨부 |

병원 3,440곳 중 영업활동이 붙는 곳은 520곳이다. 나머지 2,920곳은 담당자와 딜이 없는
미개척 고객사로 남는다. 실제 영업 조직의 프로스펙트 목록이 그렇게 생겼고, 고객사 목록의
검색·필터·페이지네이션을 제대로 시험할 수 있는 규모이기도 하다.

## 4. 날짜

모든 날짜가 기준일의 상대 오프셋이다. 스크립트에 절대 날짜 리터럴이 없다.

```text
base−120 ┃━━━━━ 과거 ━━━━━┃ base ┃━━━ 미래 ━━━┫ base+61
         ┃ 일정 완료        ┃ 진행 ┃ 예정        ┃
         ┃ 보고서 작성 완료  ┃ 미작성┃ 보고서 0건  ┃
```

- **미래 일정에는 보고서가 없다.** 검증이 이것을 0건으로 확인한다.
- **오늘 일정은 확정 보고서를 갖지 않는다.** 앞선 몇 건만 완료 처리되어 있다.
- 기준일이 `2026-08-31` 이면 미래 구간이 9월 1일 ~ 10월 31일과 겹친다.
- 견적 유효기간, 계약 종료일, 진행 중 발주의 입고 예정일만 미래 날짜를 가진다.

`--base-date` 를 바꿀 때 `--reset` 을 요구하는 이유는, 날짜 축만 옮기면 계약일과 발주일,
보고서 상태가 서로 어긋나기 때문이다. 기준일 변경은 전체 재생성이다.

`scripts.demo.check_offline` 을 여러 기준일로 돌려 구조가 유지되는 것을 확인할 수 있다.

## 5. 데이터 연결

실제 외래키만 쓴다. ERD 에 없는 관계는 만들지 않았다.

```text
customer_company ── customer_contact ── customer_contact_assignee ── member
      │
      └── sales_deal ──┬── (견적: quote_no / quote_issued_on / quote_valid_until)
           │           ├── (계약: contract_no / contract_signed_on / contract_ends_on)
           │           ├── sales_deal_item ── product
           │           ├── purchase_order ── purchase_order_item ── product
           │           ├── support_request ── support_response
           │           ├── activity ──┬── report (미팅보고서, source_activity_id)
           │           │              └── report_activity ── report (일일·주간·월간)
           │           └── document ── file
           └── sales_target (담당자 × 고객사 × 월)
```

### 지시사항 → 업무 → 보고서

`notice` 에서 `activity` 나 `report` 로 가는 외래키가 **스키마에 없다.** 네 개 링크 중 셋은
실제 FK 이고, 끊긴 한 곳만 규칙으로 잇는다.

```text
notice(DIRECTIVE) ──[notice_target: FK]──> member
                                            │  ← FK 없음. 날짜·담당자·본문 인용으로만 연결
                                            ▼
                                         activity
                                            │  ← report.source_activity_id: FK
                                            ▼
                                          report
                                            │  ← report.reviewed_by_member_id: FK
                                            ▼
                                        팀장 확인
```

`activity.note` 첫 줄에 `지시사항: {제목} (기한 M월 D일)` 을 적어 화면에서 근거가 보이게 했다.
기한이 지난 지시는 이 사슬이 끝까지 이어져 있고, 미래 지시는 일정만 있고 보고서가 없다.

## 6. 원본 데이터

### `data/sample/hospital_list_공공데이터_v2.xlsx`

8,306행 14컬럼 중 `business_status = '영업중'` 인 3,440행만 쓴다.
`customer_company` 에 자리가 있는 컬럼은 **넷뿐**이다.

| 엑셀 컬럼 | → | 변환 |
|---|---|---|
| `hospital_name` | `name` | 중복 191건은 `병원명 (시·군·구)` 로 보정 |
| `postal_code` | `postcode` | `3136.0` → `03136`. 5자리를 못 만들면 `NULL` (98% 성공) |
| `road_address` / `lot_address` | `address` | 도로명 우선, 없으면 지번 |
| 주소 첫 토큰 | `region_code` | 광역시도 화이트리스트만 통과 (100% 성공) |

나머지 10개 컬럼(`hospital_phone` · `business_type` · `hospital_type` · `business_status` ·
`medical_staff_count` · `inpatient_room_count` · `specialties` · `source_x` · `source_y` ·
`source_updated_at`)은 **대응 컬럼이 없어 버린다.** 좌표는
[`AGENTS.md`](../../AGENTS.md) 의 위치 메타데이터 규칙 대상이기도 하다.

`business_no` 는 원본에 없다. 지어내면 실존 사업자와 겹칠 수 있어 전부 `NULL` 로 둔다.

### 제품

[`data/sample/Sales_DB.xlsx`](../../data/sample/Sales_DB.xlsx) 품목리스트 시트의 11개
모델(LR/LP 체계와 판매단가)을 기준으로 50개까지 늘렸다.
`product.category_code` 는 CHECK 상 `system` / `probe` / `consumable` 셋뿐이다.

`★MEDICAL_DEVICE_PRICE_LIST_2020.7.15기준_게시용_데모.xlsx` 는 **쓰지 않는다.** 제품
카탈로그가 아니라 심평원 치료재료 급여목록(20시트, 4만여 행, A~T군 재료코드)이라
레이저장비 대리점의 `product` 에 넣으면 데이터가 앞뒤로 맞지 않는다.

### 자료실

실제 공개자료 12건의 제목·요약·출처 URL 을 상수로 두고, 실행 시점에 `.docx` 로 렌더해
Supabase Storage 에 올린다. **실행 시점에 LLM 을 부르지 않는다.** 매번 문구가 달라지면
시더가 멱등하지 않고 검증도 성립하지 않기 때문이다.

스키마에 `source_url` · `published_at` 컬럼이 없어 출처는 `description` 과 `tags`
(`출처:…` / `발행:…` / `url:…`)에 보존한다.

분류 코드는 프론트가 아는 다섯 개만 쓴다
([`useDocuments.ts`](../../frontend/src/pages/Documents/useDocuments.ts)) —
`contract` · `purchase_order` · `product_brochure` · `quote` · `other`. 다른 코드를 쓰면
화면에서 전부 '기타' 로 떨어지고 분류 탭 필터가 동작하지 않는다.

첨부는 **출처 링크가 달린 우리 팀 요약 메모**다. 식약처·심평원 원문을 복제한 것처럼 보이는
파일은 만들지 않으며, 문서 첫 줄에 그 사실을 밝힌다.

## 7. 재실행

모든 행의 id 가 `uuid5(team_id, "demo2026:{종류}:{자연키}")` 라 다시 실행해도 같은 행을
갱신할 뿐 늘어나지 않는다. 기준일은 키에 넣지 않는다 — 넣으면 날짜가 바뀔 때마다 새 행이
쌓인다.

`--reset` 은 이 규칙으로 이 시더가 만든 행만 골라 지운다. 다른 팀 데이터와 손으로 넣은
데이터는 건드리지 않는다. 삭제는 생성의 역순이다.

## 8. 검증

`scripts.verify_demo_dataset` 이 40여 개 검사를 돌린다. 수량은 엑셀과 상수에서 직접 뽑으므로
숫자를 두 곳에 적어 두지 않는다.

- **수량** — 고객사 = 엑셀 영업중 행 수, 불만 60, 공지 10 / 지시 10, 제품 50, 활성 팀장 1
- **관계** — 팀 밖 참조 0, 불만의 고객사 ≠ 딜의 고객사 0, 불만이 계약 전 딜에 붙음 0,
  미팅보고서에 근거 일정 없음 0, 지시에 수신자 없음 0, 공지에 수신자 붙음 0
- **날짜** — 미래 일정에 보고서 0, 미래 일정 완료 처리 0, 오늘 일정에 확정 보고서 0,
  개설 ≤ 견적 ≤ 계약 위반 0, 계약일보다 앞선 발주 0, 오늘·미래 일정이 아예 없으면 실패
- **값·중복** — 고객사 이름 중복 0, 우편번호 형식 위반 0, 견적/자료 번호 중복 0,
  확정 단계인데 계약일 없음 0, 발주 합계 > 계약 금액 0, 자료에 제품+딜 동시 지정 0,
  첨부의 부모가 하나가 아님 0, 담당자 없는 고객 담당자 0

DB 없이 도는 `scripts.demo.check_offline` 은 같은 불변식을 순수 파이썬으로 확인한다.
시더를 고친 뒤에는 이쪽을 먼저 돌려 공유 DB 를 건드리지 않고 걸러낸다.

## 9. 구성 파일

| 파일 | 역할 |
|---|---|
| [`scripts/seed_demo_dataset.py`](../../backend/scripts/seed_demo_dataset.py) | 진입점, `Seeder`, `reset_demo_data` |
| [`scripts/verify_demo_dataset.py`](../../backend/scripts/verify_demo_dataset.py) | 읽기 전용 검증 |
| [`scripts/demo/data.py`](../../backend/scripts/demo/data.py) | 상수 (제품·공지·지시·불만·자료실·구성원) |
| [`scripts/demo/hospitals.py`](../../backend/scripts/demo/hospitals.py) | 엑셀 → 고객사 정규화 |
| [`scripts/demo/_xlsx.py`](../../backend/scripts/demo/_xlsx.py) | 표준 라이브러리만으로 .xlsx 읽기 |
| [`scripts/demo/_docx.py`](../../backend/scripts/demo/_docx.py) | 표준 라이브러리만으로 .docx 쓰기 |
| [`scripts/demo/check_offline.py`](../../backend/scripts/demo/check_offline.py) | DB 없이 도는 검사 |

`_xlsx.py` 와 `_docx.py` 를 손으로 쓴 이유는 의존성을 늘리지 않기 위해서다. 시더가 엑셀을
한 번 읽고 문서 열두 개를 쓰는 것이 전부인데 그 때문에 `openpyxl` 과 `python-docx` 를 모든
배포에 얹을 이유가 없다. `.xlsx` 도 `.docx` 도 XML 을 담은 zip 이라 `zipfile` 로 충분하다.
PDF 는 한글 폰트를 임베드해야 해서 `.docx` 를 골랐다.

각 파일은 `python -m` 으로 직접 실행하면 자체 검사를 돈다.

## 10. 알려진 제약

- **스키마를 바꾸지 않았다.** `activity.notice_id` 가 있으면 지시 → 업무를 DB 로 이을 수
  있지만 마이그레이션은 별도 작업이다.
- **`agent_run` 과 `contract_next_meeting_suggestion` 은 만들지 않는다.** 실제 AI 실행
  로그라 손으로 넣으면 감사 기록이 오염된다. 필요하면 에이전트를 실제로 한 번 돌린다.
- **고객불만에 카테고리·우선순위·상품 컬럼이 없다.** 있는 축은 `is_urgent`(bool)와
  `status_code` 넷뿐이라 다양성은 제목·본문·응대 이력으로 만들었다.
- **불만은 반드시 딜에 붙는다.** `support_request.sales_deal_id` 가 NOT NULL 이고
  `(sales_deal_id, customer_company_id)` 복합 FK 라 딜 없는 불만은 넣을 수 없다.
- **Storage 가 설정되지 않았으면** `--skip-documents` 로 자료실을 건너뛴다.
