# 계약관리 Agent MVP — 설계 결정 기록 (ADR)

> 상태: Draft PR 오픈 전 작성. Draft PR 리뷰 결과에 따라 갱신한다.
> 브랜치: `jiyu-park/contract-agent-mvp` (base: `develop`)

## 1. 배경

계약관리 Agent는 [SalesLuv 멀티에이전트 운영 플로우](SalesLuv_멀티에이전트_운영_플로우.html)에서 계약 관련 활동(신규 등록·수정·만료)과 보고서 Agent의 승인된 최종 결과를 입력으로 받아 브리핑 생성과 다음 미팅 일정 제시를 출력하는 Agent다. 담당 테이블은 [ERD](SalesLuv_ERD.md) 기준 `contract`, `pipeline_stage`, `purchase_order`, `activity`다(단, 이 ERD 문서는 4절에서 다루는 리네임을 아직 반영하지 않은 구버전이다).

이번 MVP 범위는 다음 4가지다.

- 계약 현황 브리핑
- 만료·납품·장기 미접촉 위험 탐지
- 승인된 미팅 보고서 기반 후속 행동 제안
- 다음 미팅 필요 여부와 권장 시점 제안

계약이나 일정을 자동으로 변경하지 않고, 근거가 확인되는 브리핑과 제안까지만 만든다. 미팅 원문 분석과 딜 특성 추출은 미팅분석 Agent가 담당하고, 계약관리 Agent는 승인된 결과를 계약·일정 데이터와 결합해 후속 영업 전략을 제안하는 방식으로 역할을 나눴다.

## 2. 결정 요약

| 항목 | 결정 |
|---|---|
| 위험 판정 방식 | 규칙 기반 결정적 로직 (LLM 아님) |
| 브리핑 합성 방식 | 근거 종합·문장 생성만 LLM 인터페이스로 분리, 지금은 목업 구현체 |
| 비동기 처리 | 이번 MVP는 동기 응답. `api-conventions.md` 14절의 202+polling은 보류 |
| DB 마이그레이션 | 없음. 기존 필드만 읽어서 계산 |
| `agent_run` 기록 | 이번 MVP에서 보류. Draft PR에서 질문으로 남김 |
| 데이터 모델 기준 | `SalesDeal` (PR #32로 `Contract`에서 리네임된 이후 기준) |
| 계약 vs 딜 스코프 | 미확정 — 6절 참고 |

## 3. 결정과 근거

### 3.1 위험 판정과 브리핑 합성을 분리한다

**결정**: 만료·납품·장기 미접촉 위험 탐지와 다음 미팅 1차 판단(`contract_risk_engine.py`)은 결정적 함수로 만들고, 그 결과를 자연어 브리핑·우선순위·고객 인사이트로 종합하는 부분(`contract_briefing_llm.py`)만 LLM이 관여하는 자리로 분리했다.

**근거**: 미팅분석 Agent의 딜 승산 점수 문서([딜_승산_점수_데이터_전처리_및_AI_학습_모델.md](딜_승산_점수_데이터_전처리_및_AI_학습_모델.md))가 같은 원칙을 쓴다 — ML/LLM 결과는 화면 참고용이고, 계약 만료일처럼 확인 가능한 사실 판정은 결정적으로 유지한다. "계약이 D-15에 만료된다"는 사실은 LLM 판단에 맡기면 안 되고, "이 상황을 어떻게 요약하고 우선순위를 매길지"만 LLM이 값어치를 낸다.

**대안(기각)**: 위험 판정까지 포함해 LLM 한 번에 맡기는 안 — 이번이 이 코드베이스 최초의 LLM 연동이라 검증 부담이 크고, 위험 판정처럼 재현 가능해야 하는 로직을 비결정적 출력에 의존시키는 건 신뢰도를 낮춘다고 판단해 기각.

### 3.2 실 provider 없이 목업 LLM 클라이언트로 시작한다

**결정**: `ContractBriefingSynthesizer` Protocol을 정의하고, 지금은 `MockContractBriefingSynthesizer`만 실제로 쓴다. `get_contract_briefing_synthesizer()`는 인자 없이 목업을 반환하며, 실 provider 구현체는 아직 추가하지 않았다.

**근거**: 실 provider(모델·SDK·키 발급 일정)가 아직 확정되지 않은 상태에서 특정 provider를 코드에 미리 박아 넣으면 잘못된 가정이 남는다. 목업이 인터페이스 계약(입력: `ContractEvidenceBundle`, 출력: `ContractBriefingSynthesis`)만 정확히 지키면, 나중에 구현체 하나만 추가해 팩토리 함수만 바꾸면 되므로 지금 시점에 잃는 게 없다.

**경위**: 처음에는 `AnthropicContractBriefingSynthesizer` 스켈레톤과 `llm_provider`/`anthropic_api_key` 설정을 먼저 만들었으나, 이는 담당자와 논의 없이 임의로 정한 가정이었다. 실제로는 OpenAI 계열 모델을 쓸 예정이라는 걸 확인한 뒤 해당 코드를 전부 제거했다(커밋 이력 참고). Provider 선택은 코드에 먼저 반영할 사항이 아니라 담당자 논의로 먼저 확정해야 하는 안건이라는 걸 이번에 확인했다.

**한계**: 목업은 규칙 기반 문장 조합이라 실제 LLM처럼 새로운 표현을 만들지 않는다. 데모에서 "AI가 판단한 것"으로 보여주려면 이 한계를 발표 시 인지하고 있어야 한다.

### 3.3 임계값은 초기 추정치이며 학습된 값이 아니다

| 위험 | 임계값 | 근거 | 조정 가능 여부 |
|---|---|---|---|
| 만료 임박 | D-30/60/90 | 영업팀이 재계약 논의를 보통 시작하는 리드타임을 3단계로 나눈 추정치 | 데모 피드백 후 조정 |
| 납품 지연·임박 | 지남=high, D-7=medium | 발주 후속 조치가 필요해지는 통상 기준 | 조정 가능 |
| 장기 미접촉 | 14일(medium) / 30일(high) | 영업 사이클상 접촉 공백을 리스크로 보는 일반 휴리스틱 | 조정 가능 |
| 다음 미팅 권장 간격 | 초기 단계 7일 / 후기 단계 5일 / 확정 30일 | 파이프라인 단계별 통상 접촉 빈도 추정치 | 조정 가능 |

**근거**: 딜 승산 점수 문서가 "출력값은 공개 데이터 패턴 기반 참고 지표이며 실제 확률을 보장하지 않는다"고 명시한 것과 같은 원칙 — 여기서도 임계값이 학습이나 실측이 아니라 추정치라는 걸 숨기지 않는다.

### 3.4 이번 MVP는 동기 응답으로 만들고, `agent_run` 기록은 보류한다

**결정**: `GET /api/contracts/{id}/briefing`(Task 3에서 구현 예정)은 202+polling이 아니라 동기 응답으로 만든다. `agent_run` 테이블에 이력을 남기는 것도 지금은 하지 않는다.

**근거**: 목업 합성기는 지연이 없어 비동기로 만들 이유가 없다. `agent_run`은 이 코드베이스에서 아직 아무도 실제로 쓴 적 없는 공유 인프라라, 계약관리 Agent가 먼저 좁게 만들면 다른 4개 Agent가 각자 다른 패턴으로 재구현할 위험이 있다. 공통 인프라를 누가 어떻게 만들지는 Draft PR에서 질문으로 남긴다.

### 3.5 DB 마이그레이션 없이 기존 필드만 쓴다

**결정**: 새 테이블이나 컬럼을 만들지 않고, `sales_deal`의 `contract_ends_on`, `expected_delivery_at`, `sales_pipeline_stage_outcome_code`, `sales_pipeline_stage_position`과 `activity.starts_at`만 읽어서 계산한다.

**근거**: 마이그레이션 파일은 다른 팀원의 변경과 파일명·순서가 겹칠 위험이 있다. 이번 MVP 범위(브리핑·위험 탐지·제안)는 기존 필드 조합만으로 충분히 구현 가능하다고 판단했다.

### 3.6 일정관리 Agent 출력도 입력과 같은 원칙으로 분리한다

**결정**: `NextMeetingSuggestion` 스키마와 `build_next_meeting_suggestion()`을 추가했다. 다음 미팅이 필요 없으면 `None`을 반환하고, 필요하면 권장일·이유·의제(있으면)를 담은 형식 중립적인 값을 반환한다. 실제로 일정관리 Agent에 전달하는 통신 수단(API 호출, `agent_run` 연계 등)은 아직 만들지 않았다.

**근거**: `ApprovedMeetingInsight`(입력)와 대칭을 맞췄다 — 일정관리 Agent와의 연결 형식(텍스트 제안 vs activity 초안)이 아직 정해지지 않았다고 미확정으로 남겨뒀지만, 그렇다고 계약관리 Agent 내부에서 이 판단 자체를 안 만들어 둘 이유는 없다. "무엇을 넘길지"는 지금 결정하고 "어떻게 넘길지"만 Draft PR 이후로 미룬다.

**이유(reason) 생성 방식**: `NextMeetingCandidate.triggered_by`(위험 종류 + 접촉 주기 경과 여부)를 문장으로 매핑하는 결정적 로직이다. LLM이 아니다 — "왜 다음 미팅이 필요한지"는 근거가 명확한 사실이라 3.1의 원칙과 같다.

## 4. 발생한 이슈: SalesDeal 리네임 대응 (PR #32)

작업 도중 팀원이 `develop`에 "영업 딜과 파이프라인 데이터 모델 통합"(PR #32, 커밋 `aa27cb3`)을 머지했다. `Contract` 모델·`contracts.py`가 `SalesDeal`·`sales_deals.py`로 리네임됐고, 필드명도 다수 바뀌었다. 이미 커밋한 Task 0·1 코드가 옛 스키마를 참조하고 있어 별도 수정 커밋(`aa43c7a`)으로 대응했다.

| 예전 | 지금 |
|---|---|
| `Contract` / `ContractRead` | `SalesDeal` / `SalesDealRead` |
| `ends_on` | `contract_ends_on` |
| `amount` | `deal_amount` |
| `stage_outcome_code` | `sales_pipeline_stage_outcome_code` |
| `stage_position` | `sales_pipeline_stage_position` |
| `contract_type`(고정 Literal) | `sales_deal_type_id`(조회 테이블 FK) |
| `contract_no`(항상 존재) | `contract_no`(nullable, 계약 체결 전엔 `deal_no`가 식별자) |

시드 데이터의 계약번호 값과 UUID 생성 규칙(`uuid5(...,"contract:...")`)은 그대로 유지돼 Task 0에서 고른 12건 픽스처는 수정 없이 재사용했다.

## 5. 한계

- Task 0에서 값을 채운 12건 외 나머지 49건은 항상 "위험 없음"으로 나온다(시연 범위 한정).
- `activity`와 `sales_deal`을 직접 연결하는 필드가 없어, 장기 미접촉 판단은 같은 고객사의 최근 활동으로 근사한다 — 실제로는 다른 계약 건의 접촉일 수도 있다.
- 목업 LLM 응답은 문장 조합 수준이라 실제 LLM의 표현력과 다르다.
- DB 접속 정보(비밀번호)가 아직 확인되지 않아 Task 0~2 전부 실 데이터로 검증되지 않았다. 로컬 유닛테스트(110건, 백엔드 전체 기준)만 통과한 상태다.
- `NextMeetingSuggestion`은 아직 API 응답이나 실제 전송 경로에 연결되지 않은 순수 계산 결과다.

## 6. 미해결 질문 (Draft PR에서 확인)

1. `ApprovedMeetingInsight` 스키마(니즈·구매장벽·접촉신호·다음미팅의제)가 미팅분석 Agent의 실제 출력 방향과 맞는지.
2. 실 LLM 연동 시점과 provider(OpenAI 계열로 예정, 정확한 모델·SDK 확정 필요), API 키 발급 일정.
3. `agent_run` 기록이 필요한지, 필요하다면 동기 호출 직후 1회 INSERT로 충분한지 아니면 14절의 202+polling까지 가야 하는지.
4. **계약관리 Agent의 스코프 문제**: [영업_파이프라인_프론트_연동_제안서.md](영업_파이프라인_프론트_연동_제안서.md)를 보면 "계약현황" 화면은 `phase_code=contract`인 딜만 다룬다. 지금 위험 엔진은 `phase_code`와 무관하게 `sales_pipeline_stage_position`만 보고 있어, needs/demo 같은 초기 영업 단계 딜도 대상에 포함된다. 계약관리 Agent가 `phase_code ∈ {contract, order, closed}`로 범위를 좁혀야 하는지 확인이 필요하다.
5. 일정관리 Agent에 "다음 미팅 권장 시점"을 어떤 형태로 넘길지(텍스트 제안 vs activity 초안). `NextMeetingSuggestion` 스키마로 내용은 정리했지만, 실제 전달 수단(API 호출 방식, `agent_run` 연계 여부)은 아직 미정이다.

## 7. 이어서 진행할 작업

1. Supabase Session Pooler 접속 정보(비밀번호) 재확인 후 DB 연결 검증.
2. Task 0 시드 픽스처 스크립트를 실제 DB에 실행하고 반영 건수 확인.
3. Task 1·2 로직을 실 데이터로 스모크 테스트(유닛테스트는 이미 통과, 합성 데이터 기준).
4. Task 3: `GET /api/contracts/{id}/briefing` API 엔드포인트 구현 — 기존 `sales_deals.py`의 팀·권한 스코프 규칙 재사용, evidence 조회(결정적 엔진 입력 조립) + 합성 호출 + `NextMeetingSuggestion` 포함 + 실패 시 폴백 응답.
5. Draft PR 오픈 — 이 문서를 PR 설명에 요약해 링크하고, 6절의 미해결 질문을 리뷰 요청 포인트로 명시.
6. 리뷰 반영 후 보고서작성·일정관리 담당자와 인터페이스(입력 스키마, 다음 미팅 전달 형식) 동기화.
7. (여유 있으면) 계약 상세 화면에 브리핑 카드 프론트 연동.

## 8. 관련 커밋

브랜치 `jiyu-park/contract-agent-mvp` (base: `develop`, push됨, PR 미오픈)

- `f36323a` — 계약 위험 시연용 시드 픽스처
- `e5a68bd` — 계약 위험 판단 결정적 엔진
- `aa43c7a` — SalesDeal 리네임 대응
- `d647e2d` — 계약 브리핑 LLM 합성 인터페이스와 목업 구현체
- `3625fd4` — 확정되지 않은 앤트로픽 provider 가정 제거
- `dea4cd0` — MVP ADR 추가
