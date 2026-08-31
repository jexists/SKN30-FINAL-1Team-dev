# Database

SalesLuv 의 실제 데이터베이스 구조 정리. **36개 테이블 / 379개 컬럼 / 외래 키 96개**.

- 엔진: PostgreSQL (Supabase), 스키마 `public`
- 기준: 실제 운영 중인 DB 를 `information_schema` / `pg_catalog` 로 직접 조회한 결과
- 스키마 변경은 [`backend/sql/`](../../backend/sql/) 의 SQL 을 Supabase SQL Editor 에서 직접 실행한다 (Alembic 등 마이그레이션 도구 없음)

## 문서 사용법

| 알고 싶은 것 | 읽을 문서 |
|---|---|
| 전체 관계를 눈으로 보기 | [erd.html](erd.html) — 브라우저로 연다 |
| 전체 관계를 텍스트로 보기 | [ERD.md](ERD.md) |
| 특정 테이블의 컬럼 전체 | `tables/{테이블명}.md` |
| 외래 키 전체 목록 | [RELATIONS.md](RELATIONS.md) |
| 구조가 언제 어떻게 바뀌었는지 | [CHANGELOG.md](CHANGELOG.md) |

테이블 하나만 필요하면 `tables/` 아래 해당 파일만 읽으면 된다. 컬럼 정보는 `tables/` 에만 있고 다른 문서에 반복하지 않는다.

## 테이블 목록

### workspace — 조직·사용자·공지

| 테이블 | 설명 |
|---|---|
| [member](tables/member.md) | 서비스에 등록된 내부 사용자와 소속 팀·권한을 관리 |
| [notice](tables/notice.md) | 팀 전체 공지와 특정 구성원 지시사항을 관리 |
| [notice_image](tables/notice_image.md) | 공지 본문에 삽입한 이미지 파일을 관리 |
| [notice_target](tables/notice_target.md) | 지시사항(DIRECTIVE)을 받을 구성원을 연결 |
| [team](tables/team.md) | CRM 을 사용하는 영업 조직 단위이자 모든 데이터의 소속 기준 |

### crm — 고객·미팅·불만

| 테이블 | 설명 |
|---|---|
| [activity](tables/activity.md) | 고객 미팅 일정과 진행 결과를 관리 |
| [activity_companion](tables/activity_companion.md) | 미팅에 동행한 내부 구성원을 연결 |
| [customer_company](tables/customer_company.md) | 영업 대상 고객 회사의 기본 정보와 주소를 관리 |
| [customer_contact](tables/customer_contact.md) | 고객 회사에 소속된 담당자 정보를 관리 |
| [customer_contact_assignee](tables/customer_contact_assignee.md) | 고객 담당자를 맡은 내부 구성원을 연결 |
| [support_request](tables/support_request.md) | 고객사가 제기한 불만·요청 접수 내용을 관리 |
| [support_response](tables/support_response.md) | 접수된 불만에 대한 담당자 응대 이력을 관리 |

### sales — 제품·파이프라인·거래·발주

| 테이블 | 설명 |
|---|---|
| [product](tables/product.md) | 팀이 판매하는 제품의 기본 정보와 단가를 관리 |
| [purchase_order](tables/purchase_order.md) | 거래에 필요한 제품을 공급처에 넣은 발주를 관리 |
| [purchase_order_item](tables/purchase_order_item.md) | 발주서에 포함된 제품 품목과 수량을 관리 |
| [sales_deal](tables/sales_deal.md) | 고객사와 진행하는 영업 거래와 견적·계약 정보를 관리 |
| [sales_deal_item](tables/sales_deal_item.md) | 거래 견적에 포함된 제품 품목과 수량을 관리 |
| [sales_deal_participant](tables/sales_deal_participant.md) | 거래 미팅에 참석하는 고객 담당자를 연결 |
| [sales_pipeline](tables/sales_pipeline.md) | 팀이 사용하는 영업 파이프라인 버전을 관리 |
| [sales_pipeline_stage](tables/sales_pipeline_stage.md) | 파이프라인을 구성하는 단계와 순서를 관리 |
| [sales_target](tables/sales_target.md) | 구성원별·고객사별 월 매출 목표 금액을 관리 |

### content — 보고서·자료·파일

| 테이블 | 설명 |
|---|---|
| [document](tables/document.md) | 팀이 보관하는 자료의 분류와 연결 대상을 관리 |
| [document_chunk](tables/document_chunk.md) | 자료 파일에서 추출한 검색용 텍스트 조각을 관리 |
| [document_file_audit](tables/document_file_audit.md) | 자료 파일의 업로드와 요약 승인 이력을 기록 |
| [file](tables/file.md) | 보고서와 자료에 첨부된 파일과 추출 결과를 관리 |
| [report](tables/report.md) | 미팅·업무 보고서의 본문과 검토 상태를 관리 |
| [report_activity](tables/report_activity.md) | 보고서가 다루는 미팅 일정을 연결 |

### agent — AI 에이전트

| 테이블 | 설명 |
|---|---|
| [agent_run](tables/agent_run.md) | AI 에이전트 실행의 입출력과 근거를 남기는 감사 로그 |
| [contract_next_meeting_suggestion](tables/contract_next_meeting_suggestion.md) | 거래별 AI 다음 미팅 제안의 현재 상태를 관리 |

### config — 팀별 표시 설정

| 테이블 | 설명 |
|---|---|
| [activity_action_tag](tables/activity_action_tag.md) | 팀별 미팅 후속 조치 태그 항목을 관리 |
| [activity_category](tables/activity_category.md) | 팀별 미팅 분류 표시 항목을 관리 |
| [contract_status](tables/contract_status.md) | 팀별 계약서 상태 표시 항목을 관리 |
| [customer_contact_status](tables/customer_contact_status.md) | 팀별 고객 담당자 상태 표시 항목을 관리 |
| [purchase_order_status](tables/purchase_order_status.md) | 팀별 발주 상태 표시 항목을 관리 |
| [quote_status](tables/quote_status.md) | 팀별 견적서 상태 표시 항목을 관리 |
| [sales_deal_type](tables/sales_deal_type.md) | 팀별 거래 유형 표시 항목을 관리 |

## 알아둘 점

- `team` 이 모든 데이터의 소속 기준이다. 대부분의 테이블이 `team_id` 를 가진다.
- `member.id` 는 Supabase Auth 의 `auth.users.id` 와 같은 값이고, DB 에 외래 키가 걸려 있다.
- ENUM 타입은 쓰지 않는다. 상태·구분값은 모두 `TEXT` + `CHECK` 또는 팀별 룩업 테이블(FK)이다.
- ORM(`backend/app/models/`)에는 `relationship()` 이 없다. 관계는 전부 외래 키로만 존재한다.
- `deleted_at` 이 있는 테이블은 소프트 삭제를 쓴다.
- 모든 테이블에 RLS 가 켜져 있지만 정책은 정의되어 있지 않다. 팀 범위 제한은 애플리케이션에서 한다.

## 기존 문서

[`docs/technical/SalesLuv_ERD.md`](../technical/SalesLuv_ERD.md) 는 2026-08-19 baseline 기준(26테이블 / 264컬럼)이라 현재 구조와 다르다. 최신 기준은 이 폴더의 문서다. [`docs/technical/SalesLuv_ERD_v2.md`](../technical/SalesLuv_ERD_v2.md) 는 구현되지 않은 설계안이다 (`organization` 테이블 등은 실제로 존재하지 않는다).
