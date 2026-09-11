# 계약·일정 에이전트 상세 근거

## 1. 에이전트별 역할

| 항목 | 계약관리 | 일정관리 |
| --- | --- | --- |
| 목적 | 다음 미팅 필요성과 이유를 설명하고 미팅 준비용 브리핑 제공 | 조건에 맞는 일정 후보 제공 |
| 핵심 입력 | 회사·딜 현황, 위험 신호, 최근 확정 보고서 / 브리핑에는 일정·RAG 문맥 추가 | 딜, 탐색 기간, 소요 시간, 이유, 담당자의 기존 활동 시간 |
| 핵심 출력 | risks, missing_information, recommended_actions, next_meeting_suggestion / 브리핑에는 contract_summary, source_refs | schedule_candidates, conflicts |
| LLM 역할 | 입력 근거를 바탕으로 설명·행동·미팅 조건 생성 | 후보 시간·제목·이유·우선순위 생성 |
| 실제 업무 변경 | 추천 생성만으로 계약·딜을 수정하지 않음 | 후보 생성만으로 일정을 등록하지 않음 |

## 2. 자동 추천 실행 흐름

1. 업무 API가 데이터 저장을 마친 뒤 `queue()`를 호출한다.
2. FastAPI BackgroundTasks가 `_run_pipeline()`을 실행한다.
3. LLM 설정·진행 중 실행·최근 실행 등을 확인하고 해당 딜의 입력을 준비한다.
4. 계약 실행을 AgentRun에 등록하고 공통 실행 경로로 실행한다.
5. 미팅 제안이 있으면 그 조건과 담당자의 기존 일정으로 일정 실행을 만든다.
6. 서버 후처리를 통과한 후보가 있으면 추천 테이블에 저장한다.
7. 캘린더는 저장된 추천을 조회한다.
8. 사용자가 후보를 선택해 일정 등록을 요청한다.
9. API가 추천을 선점하고 일정을 저장한 뒤 브리핑 생성을 요청한다.

시작 지점: 보고서 확정, 영업 건 생성, 단계 이동, 딜에 연결된 일정 수동 등록,
CS 상태를 in_progress로 설정하는 처리.
동일 딜의 queued/running 실행과 최근 실행을 검사하며 쿨다운은 코드상 10분이다.
항상 후보가 나온다고 보장하지 않는다. 미팅 제안 없음·후보 없음·실행 실패면 추천 저장 없이 끝날 수 있다.

공통 실행은 `agent_runs.execute()`를 통해 worker의 선점·실행 규칙을 사용한다.
별도 worker의 큐 폴링 경로도 존재한다. 따라서 모든 추천을 별도 컨테이너 worker만 처리한다고
단정하지 않는다. 파이프라인 순서 결정은 서버 코드가 맡는다.

## 3. 판단과 검증의 구체 내용

### 계약 위험

서버가 계약 만료, 견적 만료, 납기 경과, 장기 미접촉, 미해결 CS, 계약 정보 누락,
계약 후 재방문 시점 같은 신호를 계산한다.
예: 계약 종료 30일 이내, 견적 유효기한 14일 이내, 미접촉 30일 이상을 확인한다.
이것은 현재 규칙값이며 법적·업계 표준이라는 뜻이 아니다.
프롬프트는 입력에 없는 위험·약속·계약 조건을 새로 만들지 않도록 지시한다.
Pydantic이 필드·열거형·길이 등을 검사하지만 모든 의미적 정확성을 증명하지는 않는다.

### 일정 검증

현재 코드는 Asia/Seoul 평일 09:00~18:00, 과거 후보 제외, 기존 활동과 겹침 제거,
요청 소요 시간에 맞춘 길이 보정 후 재검사, 선호 날짜 범위 확인, 후보 중복 제거를 수행한다.
사용자에게 보여줄 후보는 최대 5개다. 보정 후 모든 후보가 탈락할 수 있다.
현재 선호 기간 보정·업무시간 정책을 최종 제품 정책으로 확정했다는 의미는 아니다.

### 사용자 승인 경계

추천 선점과 일정 등록을 같은 트랜잭션에서 처리해 같은 추천의 중복 등록을 방어한다.
시간 충돌은 후보 생성 때 필터링하고, 일정 등록 후 최신 일정을 다시 조회해 경고한다.
“승인 시 충돌을 검사해 등록 자체를 차단한다”라고 발표하면 현재 코드와 다르다.
브리핑 큐 등록 실패는 이미 저장된 일정을 되돌리지 않고 경고로 전달한다.

## 4. 브리핑 RAG의 실제 구현

### 검색어

`고객사명 + 일정 제목 + 조회된 딜 제목들`을 문자열로 조합하고 최대 500자로 제한한다.
별도 LLM이 검색어를 생성하는 구조가 아니다. 상품명을 별도 검색 항목으로 넣는 코드는 이 경로에 없다.

### 검색 범위

- 팀 범위, 삭제되지 않은 문서, 처리 완료 파일을 확인한다.
- 문서별 최신 처리 완료 파일을 기준으로 청크를 조회한다.
- 해당 딜 또는 고객사 연결 조건을 OR로 사용한다.
- 고객사 범위에는 그 고객사의 다른 딜에 연결된 자료도 들어갈 수 있다.
- 상품에만 연결된 자료는 이 RAG의 상품 필터로 자동 포함되는 구조가 아니다.

### 검색 방법

DocumentChunk.embedding은 PostgreSQL JSONB 필드다.
청크를 DB에서 조회한 뒤 Python에서 점수를 계산한다.
임베딩 설정과 청크 벡터가 있으면 코사인 유사도를 사용한다.
질의 임베딩을 사용할 수 없거나 해당 청크 벡터가 없으면 토큰 교집합 기반 키워드 점수를 사용한다.
양수 점수의 상위 5개 청크를 선택한다. 문서 5개가 아니라 청크 5개다.
선택 청크와 해당 파일의 저장 요약을 묶어 최대 12,000자 문맥 블록으로 전달한다.
현재 운영 환경에서 임베딩이 활성화됐는지는 확인하지 않았다.

### 생성과 출처

등록 일정·영업현황·위험 신호와 검색 문맥을 contract_agent.generate_briefing()에 전달한다.
문서 내용은 외부 자료임을 구분한 프롬프트 블록으로 넣는다.
조회하지 않은 문서 ID를 최상위 source_refs에 반환하면 제거한다.
검색 실패 시 빈 문맥으로 진행할 수 있으며, 근거가 없으면 missing_information에 남기도록 지시한다.
문서 ID 검증은 문장 단위 사실 검증이나 출처의 의미적 일치 보장이 아니다.

### 브리핑 생성 시점

일정 등록 API가 생성을 요청한다.
상세 화면은 브리핑 대상인 경우 기존 브리핑이 없을 때 생성을 요청하고 진행 상태를 조회한다.
자료 변경마다 자동으로 다시 만드는 정책은 현재 기능으로 주장하지 않는다.

## 5. 관련자료 목록과 브리핑 근거의 차이

| 구분 | 브리핑 RAG | 일정 상세 관련자료 |
| --- | --- | --- |
| 목적 | 생성에 사용할 근거 검색 | 사용자가 열어볼 자료 제공 |
| 방식 | 임베딩 또는 키워드 점수 | DB 연결 관계 조회 |
| 범위 | 딜·고객사 및 해당 고객사의 딜 | 관련자료: 딜·고객사 / 상품자료: 일정 상품·딜 상품·딜 품목 |
| 개수 | 상위 5청크 | 현재 조회 함수에는 동일한 5개 제한 없음 |
| 처리 상태 | 완료 파일 | 완료 파일 |
| 실행 기록 | 생성 입력에 검색 문맥 저장 | AgentRun 없이 별도 조회 |

상품 참고자료가 화면에 보여도 브리핑이 그 자료를 사용했다고 말할 수 없다.
업로드 후 자료 미노출 문제는 이번 작업에서 재현하거나 수정하지 않았다.
관련자료의 최종 정의와 갱신·목록 길이 정책도 아직 합의할 개선 항목이다.

## 6. 기술 선택과 공통 시스템의 관계

| 기술·요소 | 이 기능에서의 실제 용도 |
| --- | --- |
| FastAPI BackgroundTasks | 업무 저장 뒤 계약·일정 파이프라인 시작 |
| Python 서비스 파이프라인 | 계약 결과를 일정 입력으로 전달 |
| Pydantic / JSON Schema | LLM 입력 허용 목록과 출력 형태 검증 |
| httpx / OpenAI 호환 API | generate_structured()가 모델 요청 수행 |
| PostgreSQL / SQLAlchemy | 영업 데이터·실행 기록·추천·문서 청크 조회와 저장 |
| AgentRun / worker | 작업 선점, 상태·결과, 오류·재시도, 토큰 사용량 관리 |
| React / TypeScript | 추천 조회·선택과 상세 브리핑 조회 |
| RAG 검색 서비스 | 자료실 처리 결과를 브리핑 문맥으로 제공 |

프로젝트 전체는 LangChain을 사용하지만 이 계약·일정 호출은 generate_structured()의 HTTP 경로다.
LangGraph, DeepAgents 자율 위임, 전용 벡터 검색 엔진을 이 기능의 구현으로 표시하지 않는다.
현재 LLM 모델·임베딩 모델명은 설정에 따라 달라지므로 발표 전 운영값 확인이 필요하다.

## 7. 코드 근거 지도

| 발표 내용 | 파일 / 확인할 함수 |
| --- | --- |
| 계약 판단·브리핑 | [contract_management.py](../../../backend/app/agents/contract_management.py): propose_next_meeting, generate_briefing |
| 일정 생성·후처리 | [schedule_management.py](../../../backend/app/agents/schedule_management.py): run, _postprocess |
| 입출력 모델 | 위 두 파일 안에 정의 (ContractBriefingOutput, ScheduleCandidate 등 별도 contracts.py 없음) |
| 자동 연결·쿨다운 | [contract_next_meeting_pipeline.py](../../../backend/app/services/contract_next_meeting_pipeline.py): queue, _run_pipeline, _reserve |
| 위험·입력·검색어 | [contract_schedule_snapshots.py](../../../backend/app/services/contract_schedule_snapshots.py): _deal_risk_signals, build_briefing_snapshot, _briefing_search_query |
| LLM 호출 | [llm.py](../../../backend/app/services/llm.py): generate_structured |
| 실행 분기 | [agent_runs.py](../../../backend/app/services/agent_runs.py): dispatch, execute |
| 공통 실행 | [agent_worker.py](../../../backend/app/services/agent_worker.py): claim, run_claimed, _complete |
| 브리핑 RAG 문맥 | [sales_context.py](../../../backend/app/services/sales_context.py): retrieve_briefing_context, to_briefing_prompt_block |
| 검색 점수·범위 | [document_processing.py](../../../backend/app/services/document_processing.py): search_chunks, document_scopes |
| 벡터 저장 형식 | [content.py](../../../backend/app/models/content.py): DocumentChunk.embedding |
| 관련자료 별도 조회 | [activity_documents.py](../../../backend/app/services/activity_documents.py): list_for_activity |
| 승인·브리핑 시작 | [activities.py](../../../backend/app/api/activities.py): create_activity 주변 추천 선점·브리핑 생성 |
| 브리핑 조회 | [useAiBriefing.ts](../../../frontend/src/pages/Dashboard/useAiBriefing.ts) |
| 추천 조회 | [useAiSuggestions.ts](../../../frontend/src/pages/Calendar/useAiSuggestions.ts) |

## 8. 데모 시나리오와 준비할 화면

합성 데이터 예시이며 실제 고객 정보나 실행 결과가 아니다.

1. 가상 고객사와 담당자, 견적 기한이 가까운 영업 건, 확정 보고서를 준비한다.
2. 담당자의 기존 일정 일부를 채우고 업무 이벤트를 발생시킨다.
3. 캘린더에서 생성된 추천 이유·후보를 확인한다. 후보가 없으면 실행 상태와 입력을 확인한다.
4. 후보를 선택해 일정 등록을 확인한다.
5. 처리 완료된 가상 자료실 문서를 같은 딜에 연결하고 브리핑 생성 전에 준비한다.
6. 브리핑에서 요약·확인 사항·문서 출처 결과를 확인한다. 상세 화면의 실제 출처 표시 범위도 사전 점검한다.
7. 상품에만 연결된 자료는 별도 참고자료 목록과 비교한다.

필요한 캡처: 가상 영업현황 / 추천 카드 / 등록 일정과 브리핑 / 연결된 자료.
운영 모델명·실제 생성 결과·실패 케이스·자료 처리 완료 여부를 발표 전에 확인한다.
데모용 자료 업로드와 LLM 실행은 이번 문서 작업에 포함하지 않았다.

## 9. 평가 계획과 확인된 검증의 차이

이전 폴더 이관에서 관련 테스트 167개 통과, 외부 연동 5개 제외를 확인했다.
이 수치는 폴더 이관 회귀 검사이며 AI 품질 점수·속도·운영 성능이 아니다.
이번 발표 자료 작성에서는 해당 테스트를 다시 실행하지 않았다.

발표 전 별도 평가표를 채운다.

| 평가 항목 | 방법 | 현재 결과 |
| --- | --- | --- |
| 사실·대상 정확성 | 가상 딜과 정답 근거를 대조해 없는 조건·다른 딜 혼입 확인 | 미측정 |
| 미팅 유용성 | 목표·질문·준비 행동의 구체성을 사람이 평가 | 미측정 |
| 일정 조건 준수 | 과거·업무시간·겹침·기간·소요 시간 조건별 후보 검사 | 실출력 평가 미측정 |
| 출처 정확성 | 조회된 문서 ID와 주장 근거를 각각 확인 | 실출력 평가 미측정 |
| 장애·빈 결과 | 자료 없음·검색 실패·후보 없음·중복 승인 시나리오 | 데모 검증 필요 |
| 시간·비용 | 단계별 지연과 토큰 사용량 기록 | 미측정 |

없는 계약 조건 생성, 다른 딜 정보 혼합, 근거와 다른 출처는 중대 오류로 분류하는 것을 제안한다.
구체적인 합격 기준과 평가 표본 수는 팀 합의가 필요하다.
