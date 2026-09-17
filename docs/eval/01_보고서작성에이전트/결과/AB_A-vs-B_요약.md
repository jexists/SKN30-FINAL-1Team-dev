# SalesLuv 보고서 A/B 최종 비교

194개 계획 작업을 모두 처리했습니다. 반환 응답 194개, 로컬 검증 유효 187개, 검증 실패 7개, 최종 실행 오류 0개입니다. 실행 재시도 0회, 결과 미확인 0건입니다.

생성 가용성은 A 47/53 → B 53/53입니다. 공통 생성 성공 47건 중 양쪽 절대 Judge가 유효한 동일 43건의 평균은 A 93.23, B 95.17/100입니다. 쌍대 판정은 이 점수와 독립적으로 실행했습니다. 유효한 ID와 원문 일치는 판단의 의미적 정답을 보증하지 않습니다.

B의 개선은 일일·주간·월간의 구조와 필수 정보 보존에서 두드러집니다. 공통 미팅 평균은 A 97.74 → B 96.57로 낮아졌고, 전체 공통 사실 정확성도 3.84 → 3.74/4로 낮아졌습니다. 쌍대는 B 29승·A 1승·동점 1건·검토 필요 16건(순서 불일치 13건 포함)입니다. critical은 같은 공통 집합에서 A/B 각 2건이며 아래에 모델 귀속의 한계도 표시했습니다.

## 실행과 평가 규약

A: `A-20260907-timeout180`. B: `B-20260908-attempt02`. 53개 실행 사례를 모두 유지하며 A 생성 실패 6건을 점수 0이나 쌍대 패배로 대체하지 않습니다. 생성 성공의 절대평가 100건(47 A＋53 B), 공통 생성 성공 47쌍의 독립 순서교환 쌍대평가 94건입니다. B만 생성 성공한 6건은 공통 품질 분모에 포함하지 않습니다.

Judge는 `gpt-5.6-luna`, 출력 상한 12,000, timeout 180초, SDK retry 0, 동시호출 4입니다. source-ID 레지스트리·모델 프롬프트·가중치·로컬 검증은 유지하고 `$defs.source_id` 전송 스키마만 string으로 변경했습니다. 다른 enum은 유지했고 전체 스키마 enum 최대 70개입니다. 프로토콜은 source ID v2, 전송 형식은 `source-id-string-v3`입니다.

고정 파일럿 daily01·meeting15의 8건은 194건에 포함됩니다. 8개 응답 중 7개 유효, daily01 A 1개는 후보 문장 ID를 사실 근거로 사용해 `source_authority`로 거부됐습니다. 최대 레지스트리 meeting15 4건은 모두 유효했고 공급자/API·스키마 전반 장애가 없어 나머지 186건을 진행했습니다. 검증 실패 응답을 재채점하거나 ID·인용·점수를 수리하지 않았습니다.

모델 원응답과 선택 ID는 `calls/*/attempt-*/response.json`, 정확 인용·경로·범위·해시·cutoff는 별도 `result.json`에 있습니다. 후보 passage ID는 평가 위치이며 사실 근거가 아닙니다. inherited_error는 골든 반증과 실제 입력 근거를 모두 요구합니다.

## 생성 가용성·재시도

| 유형 | arm | 유효/실행 | 첫 시도 성공 | 외부 재시도 사례 | 재시도 회복 | 최종 실패 | 실패 시도 | runtime degraded |
|---|---|---|---|---|---|---|---|---|
| 전체 | A | 47/53 | 35 | 18 | 12 | 6 | 24 | 미관측 53건 |
| 전체 | B | 53/53 | 53 | 0 | 0 | 0 | 0 | 1 |
| 미팅 | A | 32/36 | 25 | 11 | 7 | 4 | 15 | 미관측 36건 |
| 미팅 | B | 36/36 | 36 | 0 | 0 | 0 | 0 | 1 |
| 일일 | A | 10/12 | 7 | 5 | 3 | 2 | 7 | 미관측 12건 |
| 일일 | B | 12/12 | 12 | 0 | 0 | 0 | 0 | 0 |
| 주간 | A | 4/4 | 3 | 1 | 1 | 0 | 1 | 미관측 4건 |
| 주간 | B | 4/4 | 4 | 0 | 0 | 0 | 0 | 0 |
| 월간 | A | 1/1 | 0 | 1 | 1 | 0 | 1 | 미관측 1건 |
| 월간 | B | 1/1 | 1 | 0 | 0 | 0 | 0 | 0 |

B는 52건 정상 검토 완료, meeting13 1건은 `review_scope_unknown`에 따른 유효 초안 fallback입니다. B의 내부 의미 검토·수정 53회와 외부 실행 재시도 0회는 다른 지표입니다. A degraded는 메타데이터 자체가 53건 미관측이며 0으로 해석할 수 없습니다. 기존 B 원본 comparison.json의 A degraded=0 표시는 수정하지 않고 새 집계에서 정정했습니다.

## 직접·연쇄 입력 coverage

분모는 해당 유형 전체 실행 사례에 기대되는 연결입니다. 직접 연결의 분자는 최종 생성 성공한 상위 보고서에 실제 연결된 하위 제출본입니다. leaf는 미팅 원천 도달 수이며 여러 상위 보고서에서 같은 미팅이 반복 집계되므로 독립 표본 수가 아닙니다.

| 유형 | A 직접 | A leaf | B 직접 | B leaf |
|---|---|---|---|---|
| 전체 | 41/52 | 113/144 | 52/52 | 144/144 |
| 미팅 | 해당 없음 | 32/36 | 해당 없음 | 36/36 |
| 일일 | 27/36 | 27/36 | 36/36 | 36/36 |
| 주간 | 10/12 | 27/36 | 12/12 | 36/36 |
| 월간 | 4/4 | 27/36 | 4/4 | 36/36 |

월간 monthly01의 미팅 원천은 A 27/36, B 36/36입니다. 직접 입력에 들어온 연결 누계는 A 46, 최종 성공 보고서에 남은 연결은 41이며 B는 둘 다 52입니다. 누락 원천만으로 특정 사실이 작성자에게 없었다고 단정하지 않습니다. 각 사례의 expected/actual/missing 목록은 COMPARISON.json의 rows에 보존했습니다.

## 생성 토큰·측정 범위를 붙인 시간

| 지표 | A | B |
|---|---|---|
| 반환 입력 토큰 | 9,026,419 | 4,018,526 |
| 반환 출력 토큰 | 984,351 | 550,091 |
| 반환 합계 토큰 | 10,010,770 | 4,568,617 |
| 저장 사례 elapsed 합계 | 4,360.84초 — 성공 47건만 | 5,944.00초 — 전체 53건 |
| 전체 wall clock | 미관측 | 5,945.39초 |
| telemetry usage 기록 | 1160 | 380 |
| HTTP 원응답 보존 | 0 | 374 |
| cache 미관측 기록 | 1160 | 6 |

반환 토큰은 5,442,153개, 54.36% 감소했습니다. 실제 청구 비용을 산정한 값이 아닙니다. A의 시간에는 실패와 수동 복구가 빠져 있으므로 속도 비율이나 speedup을 제시하지 않습니다.

A에는 입력/출력 0/0 telemetry 7개가 있고 cache는 미관측입니다. 0/0을 실제 무사용·무청구로 간주하지 않습니다. B는 HTTP 원문이 없는 CRM 추가조회 6회의 반환 telemetry 61,727토큰을 합계에 포함했으며, 이 6회의 cache는 미관측입니다. A 진단 62,833토큰·초기 timeout probes, 첫 B DNS 실패, 이전 부분 Judge, Codex 사용량은 생성 비교에서 제외했습니다.

## 절대 품질: 공통 성공과 전체·B 단독 성공

모든 점수는 0~4 정수 항목을 사실40·필수20·구조20·후속15·가독성5로 가중한 100점 기준입니다. common_success는 공통 생성 성공 중 양쪽 절대 Judge 유효 사례만 쓰며 총점·5항목·critical 모두 같은 사례 집합입니다. invalid/missing Judge는 0점이 아닙니다.

| 유형 | 범위 | arm | 채점/생성 분모 | 총점/100 | 공통품질/65 | guide적합/35 | critical 보고서 | critical flags |
|---|---|---|---|---|---|---|---|---|
| 전체 | 동일 유효 공통 | A | 43/47 | 93.23 | 60.93 | 32.30 | 2 | 2 |
| 전체 | 동일 유효 공통 | B | 43/47 | 95.17 | 61.19 | 33.98 | 2 | 2 |
| 전체 | 전체 절대 | A | 44/47 | 93.07 | 60.80 | 32.27 | 2 | 2 |
| 전체 | 전체 절대 | B | 52/53 | 95.43 | 61.27 | 34.16 | 2 | 2 |
| 전체 | 단독 생성 성공 | B | 6/6 | 97.50 | 62.50 | 35.00 | 0 | 0 |
| 미팅 | 동일 유효 공통 | A | 31/32 | 97.74 | 63.55 | 34.19 | 2 | 2 |
| 미팅 | 동일 유효 공통 | B | 31/32 | 96.57 | 62.62 | 33.95 | 0 | 0 |
| 미팅 | 전체 절대 | A | 31/32 | 97.74 | 63.55 | 34.19 | 2 | 2 |
| 미팅 | 전체 절대 | B | 36/36 | 96.77 | 62.67 | 34.10 | 0 | 0 |
| 미팅 | 단독 생성 성공 | B | 4/4 | 97.50 | 62.50 | 35.00 | 0 | 0 |
| 일일 | 동일 유효 공통 | A | 8/10 | 86.88 | 57.50 | 29.38 | 0 | 0 |
| 일일 | 동일 유효 공통 | B | 8/10 | 95.16 | 60.62 | 34.53 | 1 | 1 |
| 일일 | 전체 절대 | A | 9/10 | 86.81 | 57.22 | 29.58 | 0 | 0 |
| 일일 | 전체 절대 | B | 11/12 | 95.57 | 60.91 | 34.66 | 1 | 1 |
| 일일 | 단독 생성 성공 | B | 2/2 | 97.50 | 62.50 | 35.00 | 0 | 0 |
| 주간 | 동일 유효 공통 | A | 3/4 | 72.50 | 48.33 | 24.17 | 0 | 0 |
| 주간 | 동일 유효 공통 | B | 3/4 | 87.08 | 53.33 | 33.75 | 1 | 1 |
| 주간 | 전체 절대 | A | 3/4 | 72.50 | 48.33 | 24.17 | 0 | 0 |
| 주간 | 전체 절대 | B | 4/4 | 87.81 | 53.75 | 34.06 | 1 | 1 |
| 월간 | 동일 유효 공통 | A | 1/1 | 66.25 | 45.00 | 21.25 | 0 | 0 |
| 월간 | 동일 유효 공통 | B | 1/1 | 76.25 | 45.00 | 31.25 | 0 | 0 |
| 월간 | 전체 절대 | A | 1/1 | 66.25 | 45.00 | 21.25 | 0 | 0 |
| 월간 | 전체 절대 | B | 1/1 | 76.25 | 45.00 | 31.25 | 0 | 0 |

동일 유효 공통 집합의 5개 항목 평균(각 4점 만점):

| 유형 | arm | 동일 사례 수 | 사실 정확성 | 필수 내용 | 목적·구조 | 판단·후속 업무 | 가독성 |
|---|---|---|---|---|---|---|---|
| 전체 | A | 43 | 3.84 | 3.51 | 3.72 | 3.65 | 4.00 |
| 전체 | B | 43 | 3.74 | 3.77 | 3.95 | 3.79 | 3.93 |
| 미팅 | A | 31 | 3.90 | 3.90 | 3.94 | 3.87 | 4.00 |
| 미팅 | B | 31 | 3.77 | 4.00 | 3.94 | 3.81 | 3.90 |
| 일일 | A | 8 | 3.88 | 2.75 | 3.62 | 3.00 | 4.00 |
| 일일 | B | 8 | 3.88 | 3.38 | 4.00 | 3.88 | 4.00 |
| 주간 | A | 3 | 3.33 | 2.00 | 2.33 | 3.33 | 4.00 |
| 주간 | B | 3 | 3.33 | 3.00 | 4.00 | 3.67 | 4.00 |
| 월간 | A | 1 | 3.00 | 2.00 | 2.00 | 3.00 | 4.00 |
| 월간 | B | 1 | 3.00 | 2.00 | 4.00 | 3.00 | 4.00 |

전체 절대·단독 생성 성공 집합의 모든 항목 평균, critical 유형별 빈도, fact origin과 각 scored_case_ids도 COMPARISON.json 및 전체 비교문서에 있습니다.

유효한 전체 절대평가의 critical 목록(공통 집합 critical 수와 구분):

| 사례 | arm | 분류 | 귀속 | Judge 이유 |
|---|---|---|---|---|
| daily10 | B | plan_as_completed | writer_error | 입력의 '논의할 예정입니다'라는 계획 상태를 '미팅 3건을 진행했습니다'라는 완료 상태로 변경했습니다. |
| meeting15 | A | material_number_date | writer_error | 보고서는 원본 설치 관련 문서에서도 날짜가 확인되지 않았다고 단정했지만, 골든과 실제 입력에서는 해당 문서를 6월 12일까지 찾기로 했을 뿐 아직 확인 결과가 없었습니다. 이는 설치일 근거의 현재 상태를 왜곡합니다. |
| meeting30 | A | cross_deal | writer_error | 주문·반품 연동 딜의 본문에 별도 CRM 딜의 제한 시범 사실을 포함해 딜 귀속을 혼재시켰습니다. |
| weekly02 | B | material_number_date | inherited_error | 세계 진실의 서비스 건수 6건과 실제 입력의 2건이 다르며, 보고서는 입력의 2건을 그대로 계승해 핵심 수치를 왜곡했습니다. |

B만 생성 성공한 6건(공통 쌍대 분모에서 제외):

| 사례 | 유형 | B 절대 점수 | B critical 보고서 여부 |
|---|---|---|---|
| daily02 | 일일 | 95.00 | False |
| daily07 | 일일 | 100.00 | False |
| meeting19 | 미팅 | 90.00 | False |
| meeting24 | 미팅 | 100.00 | False |
| meeting25 | 미팅 | 100.00 | False |
| meeting35 | 미팅 | 100.00 | False |

## 독립 쌍대 판정과 순서 민감도

각 쌍은 익명 X/Y를 교환해 독립 호출했습니다. 두 순서에서 A/B로 환산한 판정이 같을 때만 승·무승부·양쪽 부적합을 확정합니다. defer·검증 실패·순서 불일치는 review_required로 남기며 동점으로 바꾸지 않습니다.

| 유형 | 생성 공통 쌍 | A승 | B승 | 동점 | 양쪽 부적합 | review_required | 순서 불일치 | 비대상 |
|---|---|---|---|---|---|---|---|---|
| 전체 | 47 | 1 | 29 | 1 | 0 | 16 | 13 | 6 |
| 미팅 | 32 | 1 | 16 | 1 | 0 | 14 | 12 | 4 |
| 일일 | 10 | 0 | 8 | 0 | 0 | 2 | 1 | 2 |
| 주간 | 4 | 0 | 4 | 0 | 0 | 0 | 0 | 0 |
| 월간 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |

순서 불일치 사례: daily01, meeting01, meeting04, meeting08, meeting11, meeting12, meeting13, meeting15, meeting18, meeting23, meeting29, meeting30, meeting33.

## 대표 변화와 원문 근거

아래는 실제 저장된 Judge 해석과 그 선택 ID에서 파생한 원문입니다. 발췌는 원문의 연속 부분 문자열이며 점수·근거 ID를 교체하지 않았습니다. 같은 ID도 요청마다 다른 원문을 가리킬 수 있어 요청 식별자를 함께 표시합니다.

### 개선과 순서 불일치 — meeting15: A 90.0 → B 100.0

A는 아직 찾아볼 원본 설치확인서까지 이미 날짜를 확인하지 못한 것처럼 확장했습니다. B는 원본대장의 날짜 누락과 추가 문서 확인을 구분합니다. A 절대 Judge는 material_number_date·writer_error를 표시했습니다. 쌍대에서는 두 순서 모두 X를 선택해 A/B 판정이 갈렸으므로 최종 승자는 review_required입니다. 절대 점수 개선을 확정 쌍대 승리로 바꾸지 않았습니다.

- 요청 `31624a493de7` · source ID `RX0009` · report_location · 후보 X · `/candidate/report/deals/1/body` [0:256] · cutoff 2026-06-10
  - 원문 SHA-256 `da534f62dafed851a4c9fa1b72cd0a051d10ff39da028231b4534dbf3dfc6ed9` · 등록 인용 SHA-256 `c1903cc582c3390a66a095958caec62bdea72557c5cc3b12732e5eedb4f7c53b`

> 장비 10건을 대조한 결과 9건은 설치일이 일치했으나, 1건은 원본대장과 설치 관련 원본문서에서도 날짜가 확인되지 않았습니다. 해당 건은 구두로 들은 경과연수나 임의 입력으로 설치일을 확정하지 않고, 원본 설치확인서를 확인한 뒤에도 날짜의 유효성을 별도로 판단하기로 했습니다. 자료를 찾지 못하면 설치일 미확인으로 남기며, 설치일이 확인되기 전에는 보증 종료 여부도 결론 내리지 않습니다. 설치일을 수정할 경우에는 수정자와 근거 자료를 함께 남겨야 합니다.

- 요청 `31624a493de7` · source ID `gold:meeting15-f02:0` · gold · 후보 공유 · `transcripts/meeting15.txt` [2081:2163] · cutoff 2026-06-10
  - 원문 SHA-256 `e9e3ec3a1f2e34728a60ac9d04af0bc76291989be39da8a8cb6edfe8379c4814` · 등록 인용 SHA-256 `bc1c71f9ffdd285fc4f686981770c06f9bb954347ed1afe641b6ff10a336a4cb`

> 류온재: 장비 대장 쪽도 확인하고 싶습니다. 열 건을 대조했는데 아홉 건은 설치일이 맞았고, 한 건은 원본대장에도 설치일이 비어 있다고 들었습니다.

- 요청 `31624a493de7` · source ID `gold:meeting15-f04:1` · gold · 후보 공유 · `transcripts/meeting15.txt` [2464:2521] · cutoff 2026-06-10
  - 원문 SHA-256 `e9e3ec3a1f2e34728a60ac9d04af0bc76291989be39da8a8cb6edfe8379c4814` · 등록 인용 SHA-256 `ce6912e77457ddefa838fbe85f3ef48a1f7b63757511c10421e2f833dbbf400c`

> 류온재: 원본 설치확인서는 6월 12일까지 찾아보겠습니다. 찾지 못하면 날짜 미확인으로 답하면 되겠죠?

- 요청 `31624a493de7` · source ID `gold:meeting15-f04:2` · gold · 후보 공유 · `transcripts/meeting15.txt` [2561:2628] · cutoff 2026-06-10
  - 원문 SHA-256 `e9e3ec3a1f2e34728a60ac9d04af0bc76291989be39da8a8cb6edfe8379c4814` · 등록 인용 SHA-256 `ffb0b20619bb47c90c757c597f234290f6189e44156405beacb0fcc179371b2c`

> 영업 담당자: 네. 6월 12일까지 원본 설치확인서를 확인하고, 찾지 못하면 날짜 미확인으로 답하는 것으로 이해했습니다.

- 요청 `4884161a4c38` · source ID `RX0015` · report_location · 후보 X · `/candidates/X/report/deals/1/body` [90:359] · cutoff 2026-06-10
  - 원문 SHA-256 `0bdaf54514183f2dd047a75e09e306fd2bd3c3802c9c987fecb894ce5c821217` · 등록 인용 SHA-256 `6717ec1095b87bc469c0fb10d0bb7d17fcb30cf32d7d6f9f582755a745916ffc`

> 장비 대장 10건을 대조한 결과 9건은 설치일이 일치했고, 1건은 원본대장에도 설치일이 기재되어 있지 않았습니다. 해당 1건은 구두로 들은 경과연수나 임의의 날짜를 입력하지 않고 미확인으로 두기로 했습니다. 원본 설치확인서를 찾았다는 사실과 그 문서의 설치일을 유효한 날짜로 판단하는 일은 별도로 검토하며, 설치일이 확인되기 전에는 보증 종료 여부도 결론 내리지 않기로 했습니다. 설치일을 수정하는 경우에는 수정자와 근거 자료를 함께 확인할 수 있어야 한다는 기준도 확인했습니다.

### 악화 — meeting03의 공통 요약과 상세 본문 충돌

A 100점, B 80점입니다. B 상세 본문에는 6월 5일 자료 전달과 담당자가 있지만 공통 본문은 구체적 합의·후속 조치를 미확인이라고 요약합니다. Judge는 필수 내용 4점은 유지하고 사실 정확성·구조·후속 업무·가독성을 각 3점으로 낮췄습니다. 이는 필수 사실 전체 누락과 구분되는 요약 충돌입니다.

- 요청 `fa2d41e54a34` · source ID `RX0015` · report_location · 후보 X · `/candidates/X/report/deals/1/body` [948:1230] · cutoff 2026-06-01
  - 원문 SHA-256 `fa0d5f7863b9e3b1c5d51db537e3cc5a168f8ab2293be9a541787e18d5ddeee9` · 등록 인용 SHA-256 `53453578a3c07f844d092b99977f288812c4dbb49fb29a121942e0b320020ea2`

> 보관 위치·접근 권한 설명서와 부분반품 예시는 영업 담당자가 6월 5일까지 전달할 예정이라고 안내했습니다(담당: 본인, 기한: 6월 5일, 완료 기준: 요청된 두 종류의 내용이 자료에 포함되어 전달됨, 양측 합의 여부: 미확인). 서이든 책임은 자료를 받으면 보안 담당자에게 검토 요청을 올리겠다고 밝혔으나 이는 고객의 후속 예정으로, 자료 수신 후 검토 요청의 실제 제출 여부는 미확인입니다(담당: 서이든 책임, 기한: 자료 수신 후·정확한 기한 미확인, 완료 기준: 보안 담당자에게 검토 요청 제출).

- 요청 `fa2d41e54a34` · source ID `gold:meeting03-f06:0` · gold · 후보 공유 · `transcripts/meeting03.txt` [3361:3423] · cutoff 2026-06-01
  - 원문 SHA-256 `3e098414300aa2df29e1b7694e06cc00da038bd3798c26b5166828858b65d372` · 등록 인용 SHA-256 `f1b83da630f76b73950a18ce060648ed189a23485cac4b4e694ad98bb752eb76`

> 영업 담당자: 보관 위치와 접근 권한을 설명하는 자료, 그리고 부분반품 예시를 6월 5일까지 전달할 예정입니다.

### 새 작성 오류 경고 — daily10의 계획/완료 상태

B 절대 Judge는 85점과 plan_as_completed·writer_error를 표시했습니다. 실제 입력의 “논의할 예정”을 최종 일일 보고서가 미팅 3건 완료로 표현했다는 경고입니다. 이 근거는 실제 입력과 최종 답안의 상태 차이를 보입니다. 해당 미팅의 현실 완료 여부까지 사람이 확정한 판정은 아닙니다. 독립 쌍대 두 호출은 모두 B를 선택했으므로 높은 쌍대 선호가 critical 경고를 상쇄하지 않습니다.

- 요청 `cef001c7600a` · source ID `RX0001` · report_location · 후보 X · `/candidate/report/body` [0:101] · cutoff 2026-06-22
  - 원문 SHA-256 `2892bcf89569814d09cbb267f0893d3a96f01f90933712c3aebf5ef340d803f3` · 등록 인용 SHA-256 `9bf544a82d0cc85243aab172f9482f4fd8c24c330abbc3f4ec5ea9990db7130a`

> 오늘은 활동 방식이 확인되지 않은 미팅 3건을 진행하고 CRM 계약·서비스 개시 준비, ERP 연동 및 교육 보류 사항, 고객사별 CRM·API·운영지원 검토 결과를 확인했습니다.

- 요청 `cef001c7600a` · source ID `SX0007` · actual_input · 후보 X · `/candidate/actual_input/report_sources/meetings/2/common_report/body` [0:47] · cutoff 2026-06-22
  - 원문 SHA-256 `a0fb9ec5dec7cd26cbae9241588ef5a15d6b1465cf72f5496ceba74894756b7b` · 등록 인용 SHA-256 `a0fb9ec5dec7cd26cbae9241588ef5a15d6b1465cf72f5496ceba74894756b7b`

> 2026년 6월 22일 모아리빙과의 검토 내용을 세 갈래로 나누어 논의할 예정입니다.

### 입력에서 이어진 오류와 새 작성 오류의 구분

유효 절대 Judge의 inherited_error 표시 6개(fact와 critical 발생 건수, 중복 가능) 중 예: weekly02 B. Judge 이유: 세계 진실의 서비스 건수 6건과 실제 입력의 2건이 다르며, 보고서는 입력의 2건을 그대로 계승해 핵심 수치를 왜곡했습니다.

골든 반증과 해당 arm 실제 입력이 함께 등록된 경우입니다. 입력에 이미 있는 오류를 최종 작성자가 새로 만들어낸 오류와 구분한 모델 귀속이며, 의미적 타당성은 별도 검토 대상입니다.

- 요청 `8695519dd8dc` · source ID `RX0006` · report_location · 후보 X · `/candidate/report/body` [1594:1879] · cutoff 2026-06-14
  - 원문 SHA-256 `8b1b473126adf7805550b4169cf06c3b3c84bf8af34b7cef9a7d83037fe78bc0` · 등록 인용 SHA-256 `8892d44c39973e9b70b53ff4d64a6972ae0ebac3adc9e29ee6f8c8b814420b8d`

> 온유설비 서비스는 부품 주문 요청·도착·교체·기사 수리완료·고객확인을 분리 표시하기로 했으며, 부품 대기 2건에서 도착·교체 완료는 확인되지 않았습니다. 설치장비 대장 10건 중 9건은 설치일이 일치했고 1건은 원본대장에도 설치일이 없어 미확인입니다. 류온재가 원본 설치확인서를 6월 12일까지 확인하고, 찾지 못하면 설치일 미확인으로 답하기로 했습니다. 장애 대응의 30분 내 접수 안내·담당자 배정은 검토안이며 수리완료 시간이나 확정 계약조건은 아닙니다. 야간 지원과 대체 연락체계도 확정되지 않았습니다.

- 요청 `8695519dd8dc` · source ID `gold:weekly02-f07:0` · gold · 후보 공유 · `report_sources.reports[1].values.body` [468:508] · cutoff 2026-06-14
  - 원문 SHA-256 `2cb3739b595518b54c1652621999511554eb9b12df28b835a8fad09d95bba917` · 등록 인용 SHA-256 `73093f2afa6fff3490e3b398004b8f53bccd73bb4226ef28f7f58f8e56742154`

> 서비스6건 사유는 조회됐으나 담당기사 변경1건의 표시 수정이 필요합니다.

- 요청 `8695519dd8dc` · source ID `SX0015` · actual_input · 후보 X · `/candidate/actual_input/report_sources/reports/1/values/body` [1572:1959] · cutoff 2026-06-14
  - 원문 SHA-256 `51953c844560672c38b79ccdb08d4f6a5f423ddce0b609d124fce8262b4b579b` · 등록 인용 SHA-256 `51953c844560672c38b79ccdb08d4f6a5f423ddce0b609d124fce8262b4b579b`

> 온유설비 서비스 건은 부품 주문 요청, 부품 도착, 교체, 기사 수리완료, 고객확인을 서로 분리해 표시하기로 했습니다. 현재 확인된 부품 대기 서비스는 2건이며 부품 도착이나 교체 완료는 확인되지 않았습니다. 변경된 현재 담당자와 이전 방문자를 구분하고, 같은 장비의 같은 문제는 기존 이력에 연결하되 다른 문제인지 불명확하면 확인 후 연결하기로 했습니다. 무응답을 고객확인 완료로 처리하지 않으며 종결 기준은 아직 정해지지 않았습니다. 영업 담당자는 현재 담당자·이전 방문자 및 각 서비스 상태가 구분되는 화면을 6월 12일까지 전달하기로 했고, 완료 기준은 화면에서 상태가 자동으로 완료 처리되지 않는지 확인하는 것입니다. 온유설비 측 사용성 확인의 담당자·기한·완료 기준은 미확인입니다.

검토상 주의: 골든의 서비스 전체 6건과 입력·답안의 부품 대기 2건은 범주가 다릅니다. 이 인용만으로 6을 2로 왜곡했다고 확정할 수 없으며, 모델이 전체와 부분집합을 혼동했을 가능성이 있습니다. inherited_error·critical과 원래 점수는 수정하지 않고 사람 검토 대상으로 설명합니다. daily06의 “가상 정보이며 실제 노출 사고는 아님”도 접근 통제 취약점의 존재와 양립할 수 있고, daily10 B의 “본인”과 “영업 담당자”가 같은 역할일 가능성도 있어 귀속 해석을 추가 확인해야 합니다.

## 모든 실행 사례 53건

| 사례 | 유형 | A 생성 | B 생성 | A 점수 | B 점수 | 쌍대 최종 | 순서별 환산 |
|---|---|---|---|---|---|---|---|
| daily01 | 일일 | completed | completed | 미관측 | 95.00 | review_required | A,B |
| daily02 | 일일 | failed | completed | 미관측 | 95.00 | not_eligible |  |
| daily03 | 일일 | completed | completed | 91.25 | 95.00 | B | B,B |
| daily04 | 일일 | completed | completed | 91.25 | 100.00 | B | B,B |
| daily05 | 일일 | completed | completed | 91.25 | 95.00 | B | B,B |
| daily06 | 일일 | completed | completed | 81.25 | 95.00 | B | B,B |
| daily07 | 일일 | failed | completed | 미관측 | 100.00 | not_eligible |  |
| daily08 | 일일 | completed | completed | 86.25 | 100.00 | B | B,B |
| daily09 | 일일 | completed | completed | 81.25 | 100.00 | B | B,B |
| daily10 | 일일 | completed | completed | 91.25 | 85.00 | B | B,B |
| daily11 | 일일 | completed | completed | 86.25 | 미관측 | B | B,B |
| daily12 | 일일 | completed | completed | 81.25 | 91.25 | review_required |  |
| meeting01 | 미팅 | completed | completed | 미관측 | 100.00 | review_required | B,A |
| meeting02 | 미팅 | completed | completed | 82.50 | 100.00 | B | B,B |
| meeting03 | 미팅 | completed | completed | 100.00 | 80.00 | B | B,B |
| meeting04 | 미팅 | completed | completed | 100.00 | 88.75 | review_required | B,A |
| meeting05 | 미팅 | completed | completed | 100.00 | 86.25 | B | B,B |
| meeting06 | 미팅 | completed | completed | 95.00 | 100.00 | B | B,B |
| meeting07 | 미팅 | completed | completed | 100.00 | 100.00 | review_required |  |
| meeting08 | 미팅 | completed | completed | 100.00 | 90.00 | review_required | B,A |
| meeting09 | 미팅 | completed | completed | 100.00 | 100.00 | review_required |  |
| meeting10 | 미팅 | completed | completed | 100.00 | 90.00 | B | B,B |
| meeting11 | 미팅 | completed | completed | 100.00 | 100.00 | review_required | B,A |
| meeting12 | 미팅 | completed | completed | 100.00 | 86.25 | review_required | equivalent,B |
| meeting13 | 미팅 | completed | completed | 100.00 | 100.00 | review_required | A,B |
| meeting14 | 미팅 | completed | completed | 100.00 | 100.00 | A | A,A |
| meeting15 | 미팅 | completed | completed | 90.00 | 100.00 | review_required | A,B |
| meeting16 | 미팅 | completed | completed | 100.00 | 96.25 | B | B,B |
| meeting17 | 미팅 | completed | completed | 100.00 | 100.00 | B | B,B |
| meeting18 | 미팅 | completed | completed | 100.00 | 100.00 | review_required | B,A |
| meeting19 | 미팅 | failed | completed | 미관측 | 90.00 | not_eligible |  |
| meeting20 | 미팅 | completed | completed | 95.00 | 100.00 | B | B,B |
| meeting21 | 미팅 | completed | completed | 100.00 | 100.00 | B | B,B |
| meeting22 | 미팅 | completed | completed | 100.00 | 100.00 | B | B,B |
| meeting23 | 미팅 | completed | completed | 100.00 | 83.75 | review_required | A,B |
| meeting24 | 미팅 | failed | completed | 미관측 | 100.00 | not_eligible |  |
| meeting25 | 미팅 | failed | completed | 미관측 | 100.00 | not_eligible |  |
| meeting26 | 미팅 | completed | completed | 96.25 | 100.00 | B | B,B |
| meeting27 | 미팅 | completed | completed | 100.00 | 100.00 | B | B,B |
| meeting28 | 미팅 | completed | completed | 100.00 | 100.00 | equivalent | equivalent,equivalent |
| meeting29 | 미팅 | completed | completed | 100.00 | 96.25 | review_required | A,B |
| meeting30 | 미팅 | completed | completed | 85.00 | 96.25 | review_required | equivalent,B |
| meeting31 | 미팅 | completed | completed | 100.00 | 100.00 | B | B,B |
| meeting32 | 미팅 | completed | completed | 100.00 | 100.00 | B | B,B |
| meeting33 | 미팅 | completed | completed | 100.00 | 100.00 | review_required | A,B |
| meeting34 | 미팅 | completed | completed | 100.00 | 100.00 | B | B,B |
| meeting35 | 미팅 | failed | completed | 미관측 | 100.00 | not_eligible |  |
| meeting36 | 미팅 | completed | completed | 86.25 | 100.00 | B | B,B |
| monthly01 | 월간 | completed | completed | 66.25 | 76.25 | B | B,B |
| weekly01 | 주간 | completed | completed | 미관측 | 90.00 | B | B,B |
| weekly02 | 주간 | completed | completed | 66.25 | 85.00 | B | B,B |
| weekly03 | 주간 | completed | completed | 80.00 | 85.00 | B | B,B |
| weekly04 | 주간 | completed | completed | 71.25 | 91.25 | B | B,B |

## Judge 사용량·실패 보존

| 지표 | 새 동일 형식 전체 실행 | 이전 부분 기술 실행 |
|---|---|---|
| 시작 작업 | 194 | 49 |
| 원응답 | 194 | 45 |
| 유효 | 187 | 7 |
| 검증 실패 | 7 | 38 |
| 결과 미확인 | 0 | 4 |
| 입력 토큰 | 6,920,648 (미관측 0) | 703,846 (미관측 4) |
| 출력 토큰 | 245,467 (미관측 0) | 106,275 (미관측 4) |
| 합계 토큰 | 7,166,115 (미관측 0) | 810,121 (미관측 4) |
| cache read 토큰 | 41,372 (미관측 0) | 84,084 (미관측 4) |

새 실행의 provider 응답 ID 194개를 보존했습니다. 모델 응답 metadata 식별자는 {'gpt-5.6-luna': 194}입니다. 새 Judge 요청별 elapsed 합계는 2525.99초이며 동시 실행한 요청들의 합계라 wall clock이 아닙니다.

이전 AB-20260908-reviewed는 49건 시작·45건 반환·7건 유효·38건 인용 실패·4건 결과/사용량 미확인인 중단된 기술 실행입니다. 이번 품질 점수·승패에 섞지 않았습니다. AB-20260908-source-ids는 194건 준비만 한 무호출 계획으로 그대로 보존했습니다. 이전 미확인 4건의 청구량을 0으로 가정하지 않습니다.

| 검증 실패 코드 | 새 응답 수 |
|---|---|
| source_authority | 5 |
| report_passages_required | 1 |
| citation_source_id_only | 1 |

각 실패의 case·arm·job·원응답 해시·usage는 COMPARISON.json의 judge_final.invalid_jobs 및 judge-attempts.json에 있습니다. 원응답 완전 수신 후 점수 개선을 위한 재호출은 없습니다.

## 해석 한계

- 생성·runtime reviewer와 Judge는 별도 호출이고 쌍대도 독립 호출입니다. 다만 생성과 Judge가 같은 gpt-5.6-luna여서 모델 계열의 자기 선호 가능성까지 독립적이지는 않습니다.
- 합성된 연결 4주 이야기이며 월간은 1건입니다. 53개 독립 표본·통계적 유의성·월간 일반화를 주장하지 않습니다.
- B는 프롬프트와 runtime이 함께 바뀐 종단간 시스템 비교입니다. 상위 보고서가 받은 자기 arm의 하위 입력과 coverage도 달라 개별 수정의 인과효과로 분해할 수 없습니다.
- 엄격한 ID·출처·해시 검증은 기계적 인용 계약 검증입니다. 모든 모델 판단을 사람이 확인한 정답으로 표현하지 않습니다. invalid Judge 제외로 공통 유효 집합에도 선택 편향 가능성이 남습니다.
- B 실제 생성 53건, A 실제 생성 성공 47건의 원문·MD·원래 FINAL·동결 자료는 수정하지 않았습니다. Judge에는 DB나 계정이 필요하지 않았습니다.

## 산출물과 무결성

[기계 집계 JSON](COMPARISON.json) · [전체 비교와 모든 인용](comparisons/2c445c18c5ede0b6cab8ec4476b21af6a1c7c6d0053bf1aa33e5818d6f387a63.md) · [계획](plan.json) · [시도·provider ID·usage](judge-attempts.json) · [이전 기술 Judge usage](old-partial-technical-usage.json) · [파일럿](pilot-verification.json) · [프로토콜](protocol-note.md) · [최종 검증](verification/final-verification.json) · [파일 해시 목록](model-and-protocol-hashes.json)

| 검사 | 결과 |
|---|---|
| 194 요청 및 반환 원응답/파생 결과 | PASS |
| 보존 파일 해시 | 3461개 변경 없음 |
| 원응답 선택·주장·이유·점수 보존 | PASS |
| 공통 총점·모든 항목·critical 동일 사례 집합 | PASS |
| 현재 코드/사전 스냅샷 일치 | PASS |

Judge 코드 SHA-256 `04988a719dca9ffad5b8e4146b51272a27bddfc0a9eed1f76943f70d8435aea6`

계획 SHA-256 `6bfbfcea502b1229f50657484bad1054b7a208b51e246291ec187e6673a2f11c`

프롬프트 SHA-256 `c6bda9f2142820dcbed78f5cba4c620ec7200559a1e4bb9a4f19d8eaf0a77645`

생성물 대규모 감사는 기존 통과 결과와 한계를 verification/prior에 원본 그대로 복사했으며 재실행하지 않았습니다. helper 파일 전체는 B의 generate_structured 경로에서 다르지만 실제 Judge가 사용하는 configured_chat_model·설정 검증·오류 분류 영역은 byte-identical임을 확인했습니다. 원래 FINAL을 수정하지 않았습니다. 브랜치 전환·커밋·푸시·새 의존성·하위 작업 생성·완료 작업 재사용 없이 이 단일 과제의 처리를 마쳤습니다.
