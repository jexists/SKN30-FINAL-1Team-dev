# SalesLuv 최종 ERD

> 범위: 팀원 화면과 SalesLuv 멀티에이전트 운영 흐름<br>
> 상태: 구현 전 최종 설계안<br>
> 권고 규모: **20테이블 / 200컬럼**

## 설계 원칙

- 독립적으로 조회·수정되는 업무 데이터와 1:N·N:M 이력은 별도 테이블로 둔다.
- 화면 표시값, 합계, 최근 접촉, 다음 일정, 진행률은 원천 데이터에서 계산한다.
- 보고 양식은 코드로 관리하고 작성 시점의 `template_snapshot`을 보고서에 저장한다.
- 보고 첨부와 문서 버전은 공통 `files` 테이블로 관리한다.
- LLM 실행 자체의 상태·모델·프롬프트·입출력·근거는 `agent_runs`에 기록한다.
- `?`는 NULL 허용, `PK`는 기본키, `FK`는 외래키, `UQ`는 중복 불가다.

## LLM 에이전트 연결

- 고객관리 Agent → `customer_companies`, `customer_contacts`, `support_requests`, `activities`
- 보고서 Agent → `reports`, `report_activities`, `files`
- 계약관리 Agent → `contracts`, `pipeline_stages`, `orders`, `activities`
- 일정관리 Agent → `activities`, `activity_companions`
- 자료요약 Agent → `documents`, `files`
- 모든 Agent 실행 이력 → `agent_runs`

## 1. 조직·사용자

### 1. `teams / 팀` — 3개

다른 팀의 고객·계약·자료가 섞이지 않도록 데이터 접근 범위를 정한다.

- `id PK` — 팀을 식별하는 기본키
- `name` — 화면에 표시할 팀 이름
- `created_at` — 팀이 생성된 시각

### 2. `members / 팀원` — 9개

로그인 계정과 소속 팀, 권한, 업무 담당자를 관리한다.

- `id PK` — 팀원을 식별하는 기본키
- `team_id FK` — 팀원이 소속된 팀
- `login_id UQ` — 중복되지 않는 로그인 아이디
- `password_hash` — 비밀번호를 안전하게 저장한 해시
- `display_name` — 화면과 보고서에 표시할 이름
- `role_code` — 팀원·팀장 등 권한 구분
- `job_title?` — 팀원의 직책 또는 직급
- `active` — 로그인과 업무 배정 가능 여부
- `created_at` — 계정이 생성된 시각

## 2. 고객·CRM

### 3. `customer_companies / 고객사` — 5개

여러 고객 담당자가 소속되는 거래처 회사 정보를 관리한다.

- `id PK` — 고객사를 식별하는 기본키
- `team_id FK` — 고객사를 관리하는 내부 팀
- `name` — 고객사명
- `region_code?` — 지역별 검색·매출 분석 코드
- `created_at` — 고객사가 등록된 시각

### 4. `customer_contacts / 고객 담당자` — 12개

실제로 연락하고 미팅하는 고객 측 인물 정보를 관리한다.

- `id PK` — 고객 담당자를 식별하는 기본키
- `company_id FK` — 담당자가 소속된 고객사
- `owner_member_id FK` — 관계를 담당하는 내부 팀원
- `name` — 고객 담당자 이름
- `department?` — 고객 담당자의 소속 부서
- `job_title?` — 고객 담당자의 직책
- `email?` — 이메일 주소
- `phone` — 연락 가능한 전화번호
- `status_code?` — 잠재·활성·휴면 등 고객 상태
- `source_code?` — 소개·문의 등 고객 유입 경로
- `memo?` — 고객 관련 추가 참고사항
- `registered_at` — 고객 담당자가 등록된 시각

### 5. `products / 상품` — 4개

일정·계약·발주에서 동일한 상품을 일관되게 참조한다.

- `id PK` — 상품을 식별하는 기본키
- `team_id FK` — 상품을 관리하는 팀
- `name` — 상품명
- `active` — 현재 판매·선택 가능한 상품인지 표시

### 6. `notices / 공지·지시` — 12개

팀 공지와 개인 업무 지시, 기한 정보를 전달한다.

- `id PK` — 공지·지시를 식별하는 기본키
- `team_id FK` — 공지가 속한 팀
- `author_member_id FK` — 공지를 작성한 팀원
- `recipient_member_id? FK` — 개인 수신자이며, 없으면 팀 공지
- `tag?` — 공지·긴급·업무 등 분류 태그
- `title` — 목록에 표시할 제목
- `body` — 공지·지시 본문
- `image_storage_key?` — 첨부 이미지의 저장 위치
- `image_alt?` — 이미지 접근성을 위한 대체 설명
- `published_at` — 공지가 게시된 시각
- `due_at?` — 업무 지시의 실제 마감 시각
- `due_text?` — “매일 18:00”처럼 작성자가 입력한 자유형 기한 안내

### 7. `activities / 일정·업무` — 22개

미팅·방문·전화·할 일과 후속 업무를 하나의 일정 흐름으로 관리한다.

- `id PK` — 일정·업무를 식별하는 기본키
- `team_id FK` — 일정이 속한 팀
- `owner_member_id FK` — 일정을 담당하는 팀원
- `customer_contact_id? FK` — 일정의 주요 고객 담당자
- `end_user_contact_id? FK` — 실사용자가 주요 담당자와 다를 때 연결
- `product_id? FK` — 일정에서 다루는 상품
- `contract_id? FK` — 일정과 관련된 계약
- `order_id? FK` — 일정과 관련된 발주
- `activity_type` — 미팅·업무 등 핵심 활동 유형
- `category_code` — 방문·데모·내부업무 등 화면 분류
- `title` — 캘린더와 목록에 표시할 일정명
- `starts_at` — 일정 시작 시각
- `ends_at?` — 일정 종료 시각
- `all_day` — 종일 일정 여부
- `due_at?` — 완료해야 하는 업무 마감 시각
- `location?` — 방문·미팅 장소
- `action_tag?` — 데모 완료·견적 완료 등 후속조치 태그
- `completed_at?` — 일정·업무를 완료한 시각
- `note?` — 일정 관련 메모
- `deleted_at?` — 기록을 보존하는 소프트 삭제 시각
- `created_at` — 일정이 생성된 시각
- `updated_at` — 일정이 마지막으로 수정된 시각

### 8. `activity_companions / 일정 동행자` — 2개

한 일정에 여러 팀원이 참여하는 N:M 관계를 관리한다.

- `activity_id PK/FK` — 동행자가 참여하는 일정
- `member_id PK/FK` — 해당 일정에 동행하는 팀원

### 9. `support_requests / C/S 요청` — 9개

고객 문의·불편·지원 요청과 처리 상태를 관리한다.

- `id PK` — C/S 요청을 식별하는 기본키
- `team_id FK` — 요청을 처리하는 팀
- `customer_contact_id FK` — 요청과 관련된 고객 담당자
- `assignee_member_id FK` — 요청 처리 담당 팀원
- `title` — 요청 내용을 요약한 제목
- `body` — 고객 요청의 상세 내용
- `is_urgent` — 긴급 처리 필요 여부
- `status_code` — 접수·처리 중·완료 등 처리 상태
- `registered_at` — 요청이 접수된 시각

### 10. `support_responses / C/S 답변 이력` — 5개

한 C/S 요청에서 여러 번 발생하는 대응 과정을 시간순으로 보존한다.

- `id PK` — 답변 이력을 식별하는 기본키
- `request_id FK` — 답변이 속한 C/S 요청
- `responder_member_id FK` — 답변을 작성한 팀원
- `body` — 답변 또는 처리 내용
- `responded_at` — 답변이 등록된 시각

## 3. 계약·발주·매출

### 11. `pipeline_stages / 영업 단계` — 6개

팀별 계약 보드의 단계·순서·색상과 매출 인정 기준을 관리한다.

- `id PK` — 영업 단계를 식별하는 기본키
- `team_id FK` — 단계 설정을 사용하는 팀
- `name` — 화면에 표시할 단계명
- `tone` — 단계 배지·컬럼의 표시 색상
- `outcome_code` — 진행중·확정·취소 등 매출 판정값
- `position` — 보드에서 표시할 단계 순서

### 12. `contracts / 계약` — 21개

고객사와의 영업·계약 건, 금액, 단계, 종료·납품 정보를 관리한다.

- `id PK` — 계약을 식별하는 기본키
- `team_id FK` — 계약을 관리하는 팀
- `contract_no` — 사용자에게 보이는 계약번호
- `customer_company_id FK` — 계약 상대 고객사
- `contact_id? FK` — 계약과 관련된 고객 담당자
- `owner_member_id FK` — 계약 담당 내부 팀원
- `product_id? FK` — 계약 대상 상품
- `stage_id FK` — 현재 영업 보드 단계
- `title` — 계약명
- `description?` — 계약 내용 요약
- `contract_type` — 신규·갱신·유지보수 등 계약 유형
- `amount` — 계약금액과 매출 분석의 원천
- `contract_date` — 계약 체결 또는 기준일
- `ends_on?` — 계약 종료일·갱신 예정 판단 기준
- `warranty_terms?` — 보증기간 또는 보증 조건
- `expected_delivery_at?` — 납품 예정 일시
- `memo?` — 계약 관련 내부 메모
- `position` — 같은 단계 안에서의 카드 표시 순서
- `deleted_at?` — 참조를 보존하는 소프트 삭제 시각
- `created_at` — 계약이 생성된 시각
- `updated_at` — 계약이 마지막으로 수정된 시각

### 13. `orders / 발주` — 15개

계약 이후 발생하는 발주와 공급처·납기·입고 진행 상태를 관리한다.

- `id PK` — 발주를 식별하는 기본키
- `team_id FK` — 발주를 관리하는 팀
- `order_no` — 사용자에게 보이는 발주번호
- `contract_id? FK` — 발주와 연결된 계약
- `customer_company_id FK` — 발주 대상 고객사
- `owner_member_id FK` — 발주 담당 내부 팀원
- `supplier_name` — 물품을 공급하는 공급처명
- `stage_code` — 발주 접수부터 납품 완료까지의 상태
- `ordered_on` — 발주가 등록된 날짜
- `due_on` — 발주의 약정 납기일
- `expected_receipt_on` — 입고 예상일
- `memo?` — 발주 관련 내부 메모
- `deleted_at?` — 기록을 보존하는 소프트 삭제 시각
- `created_at` — 발주가 생성된 시각
- `updated_at` — 발주가 마지막으로 수정된 시각

### 14. `order_items / 발주 품목` — 6개

한 발주에 포함되는 여러 상품·수량·단가를 행 단위로 관리한다.

- `id PK` — 발주 품목을 식별하는 기본키
- `order_id FK` — 품목이 속한 발주
- `product_id FK` — 발주한 상품
- `quantity` — 발주 수량
- `unit_price` — 상품 한 개의 단가
- `position` — 품목 목록의 표시 순서

### 15. `sales_targets / 월별 영업 목표` — 5개

담당자·고객사·월 단위의 매출 목표와 달성률 계산 기준을 관리한다.

- `id PK` — 목표를 식별하는 기본키
- `owner_member_id FK` — 목표를 담당하는 팀원
- `customer_company_id FK` — 목표가 설정된 고객사
- `target_month` — 목표가 적용되는 연·월
- `target_amount` — 해당 월의 목표금액

같은 담당자·고객사·월의 목표는 하나만 존재하며 `target_amount >= 0`으로 제한한다.

## 4. 보고·자료실

### 16. `reports / 보고서` — 20개

LLM이 만든 초안과 사람이 수정·검토·승인한 최종 보고서를 함께 보존한다.

- `id PK` — 보고서를 식별하는 기본키
- `team_id FK` — 보고서가 속한 팀
- `author_member_id FK` — 보고서를 작성·제출한 팀원
- `recipient_member_id? FK` — 보고서를 검토할 대상자
- `template_snapshot JSONB` — 작성 당시 사용한 보고 양식
- `source_activity_id? FK` — 미팅 보고서의 원천 일정
- `report_kind` — 미팅·일간·주간·월간 보고 구분
- `report_date` — 보고 기준일
- `period_start?` — 기간 보고의 시작일
- `period_end?` — 기간 보고의 종료일
- `status_code` — 임시저장·검토대기·승인·반려 상태
- `content JSONB` — 양식에 따라 작성된 보고서 본문
- `transcript?` — STT 또는 직접 입력된 미팅 원문
- `source_snapshot? JSONB` — 보고서 생성 당시 고객·계약·일정 정보
- `ai_evidence? JSONB` — LLM 출력에 사용한 근거와 출처
- `note?` — 작성자·검토자가 남긴 추가 메모
- `reviewed_by_member_id? FK` — 실제 검토·승인한 팀원
- `reviewed_at?` — 검토·승인 또는 반려가 처리된 시각
- `created_at` — 보고서가 생성된 시각
- `updated_at` — 보고서가 마지막으로 수정된 시각

### 17. `report_activities / 보고서 포함 활동` — 2개

일·주·월 보고서에 여러 활동을 연결하는 N:M 관계다.

- `report_id PK/FK` — 활동을 포함하는 보고서
- `activity_id PK/FK` — 보고서에 포함된 일정·업무

### 18. `documents / 자료실 문서` — 12개

자료실에서 문서의 제목·분류·업무 연결과 파일 버전 묶음을 관리한다.

- `id PK` — 자료실 문서를 식별하는 기본키
- `team_id FK` — 문서가 속한 팀
- `created_by_member_id FK` — 문서를 처음 등록한 팀원
- `document_no` — 자료실과 계약서에 표시할 문서번호
- `category_code` — 계약서·발주서·교육자료 등 문서 분류
- `title` — 자료실 목록에 표시할 제목
- `description?` — 문서 내용에 대한 설명
- `customer_company_id? FK` — 문서와 관련된 고객사
- `contract_id? FK` — 문서와 관련된 계약
- `order_id? FK` — 문서와 관련된 발주
- `tags JSONB` — 검색·분류용 문서 태그 목록
- `created_at` — 논리 문서가 생성된 시각

### 19. `files / 파일·문서 버전` — 13개

보고서 첨부파일과 자료실 문서 버전을 공통 파일 메타데이터로 관리한다.

- `id PK` — 파일을 식별하는 기본키
- `report_id? FK` — 보고서 첨부파일일 때 연결되는 보고서
- `document_id? FK` — 문서 버전일 때 연결되는 자료실 문서
- `version_no?` — 자료실 문서의 버전 번호
- `file_name` — 사용자가 확인하는 원본 파일명
- `storage_key UQ` — 실제 파일 저장소 위치를 찾는 고유 키
- `media_type?` — PDF·PPTX 등 MIME 유형
- `byte_size` — 파일 크기
- `processing_status` — 업로드·OCR·추출 처리 상태
- `extracted_text?` — 자료요약 Agent가 사용할 추출 텍스트
- `uploaded_by_member_id FK` — 파일을 업로드한 팀원
- `note?` — 문서 버전 또는 파일 관련 메모
- `uploaded_at` — 파일이 업로드된 시각

제약:

- `report_id`, `document_id` 중 정확히 하나만 존재한다.
- 문서 버전이면 `version_no >= 1`, 보고 첨부면 `version_no IS NULL`이다.
- `UNIQUE(document_id, version_no)`와 `UNIQUE(storage_key)`를 적용한다.

## 5. LLM Agent

### 20. `agent_runs / 에이전트 실행 이력` — 17개

각 LLM Agent 실행의 입력·출력·모델·근거·실패 상태와 에이전트 간 호출 관계를 추적한다.

- `id PK` — 에이전트 실행 한 건의 기본키
- `team_id FK` — 실행이 속한 팀 범위
- `parent_run_id? FK` — 다른 Agent가 호출한 경우 상위 실행
- `requested_by_member_id? FK` — 실행을 직접 요청한 팀원
- `agent_code` — 고객관리·보고서·계약·일정·자료요약 Agent 구분
- `trigger_code` — 미팅 업로드·계약 변경 등 실행 계기
- `idempotency_key?` — 사용자가 시작한 같은 실행 요청의 중복 처리를 막는 키
- `status_code` — 대기·실행 중·완료·실패 상태
- `model_name` — 실행에 사용한 LLM 모델
- `prompt_version` — 적용한 시스템 프롬프트 버전
- `source_refs JSONB` — 고객·일정·계약·문서 등 참조 원천 ID 목록
- `input_snapshot JSONB` — LLM에 전달된 정제 입력
- `output_snapshot? JSONB` — LLM이 생성한 원본 결과
- `evidence? JSONB` — 결과를 뒷받침한 문서·데이터 근거
- `error_message?` — 실패한 경우 원인 메시지
- `started_at?` — 대기 상태가 끝나고 실행을 시작한 시각
- `finished_at?` — 완료 또는 실패한 시각

`parent_run_id`로 Agent 간 교류를 표현한다. 고객관리 Agent의 감정분석 결과가 계약관리 Agent 실행을 호출하면 두 실행을 부모·자식으로 연결한다.

사용자가 시작한 실행은 `requested_by_member_id`, `idempotency_key` 조합을 중복 불가로 둔다. Agent 내부 호출은 `idempotency_key`를 사용하지 않는다.

`input_snapshot`에는 비밀번호나 불필요한 개인정보 원문을 복제하지 않고, 권한 검사를 통과한 정제 데이터만 저장한다.

별도의 `agent_tool_calls` 테이블은 지금 만들지 않는다. 도구별 입력·출력을 장기간 감사해야 하는 운영·컴플라이언스 요구가 생길 때만 분리한다.

## 보류 항목

- 견적현황은 유스케이스의 입력 필드·상태 전이가 확정될 때 `quotes` 테이블을 추가한다.
- 알림은 공지와 다른 개인별 읽음·삭제 이력이 실제 API로 확정될 때 `notifications` 테이블을 추가한다.
- 팀장이 보고 양식을 직접 생성·수정할 때 `report_templates` 테이블을 다시 분리한다.
- 에이전트의 도구 호출 단위 감사가 필요할 때 `agent_tool_calls`를 추가한다.
