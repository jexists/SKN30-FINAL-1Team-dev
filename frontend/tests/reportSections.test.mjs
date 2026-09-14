import assert from 'node:assert/strict'
import test from 'node:test'

import { reportSections } from '../src/shared/reportSections.ts'

// backend/app/agents/reports/skills/sales-meeting-report/references/examples.md 의 꼴
const DEAL_BODY = `**미팅 목적**

재고관리 SaaS 도입 조건을 확인하기 위해 한빛유통 최 팀장과 온라인 미팅을 진행했습니다.

**논의 내용**

30계정 기준 월 90만원, 부가세 별도 견적을 전달했습니다.

**고객 요구**

최 팀장은 보안 검토를 통과하면 10월부터 사용해 볼 수 있다고 밝혔습니다. 예산은 아직 미승인 상태입니다.

**합의사항**

해당사항 없음 (제공된 자료에 관련 내용 없음)

**후속 조치**

- **보안 체크리스트 전달** · 담당: 본인 · 기한: 내일·기준일 미확인 · 완료 기준: 미확인 · 상태: 합의`

test('딜별 본문은 다섯 구획과 후속 조치 이름표로 읽힌다', () => {
  const sections = reportSections(DEAL_BODY)
  assert.ok(sections)
  assert.deepEqual(
    sections.map((section) => section.heading),
    ['미팅 목적', '논의 내용', '고객 요구', '합의사항', '후속 조치'],
  )

  // 서술 구획은 문단 그대로입니다. 후속 조치만 이름표가 붙습니다.
  assert.equal(sections[0].body, '재고관리 SaaS 도입 조건을 확인하기 위해 한빛유통 최 팀장과 온라인 미팅을 진행했습니다.')
  assert.equal(sections[0].actions, undefined)
  assert.equal(sections[3].body, '해당사항 없음 (제공된 자료에 관련 내용 없음)')

  const [action] = sections[4].actions
  assert.equal(action.task, '보안 체크리스트 전달')
  assert.deepEqual(action.fields, [
    { label: '담당', value: '본인' },
    // 값 안의 가운뎃점은 구분자가 아닙니다. 앞뒤 공백이 있어야 자릅니다.
    { label: '기한', value: '내일·기준일 미확인' },
    { label: '완료 기준', value: '미확인' },
    { label: '상태', value: '합의' },
  ])
})

test('파이프 구분자와 이름표 없는 앞머리도 읽는다', () => {
  const sections = reportSections(
    `**후속 조치**

- 요청 | 보안 체크리스트 전달 | 담당: 본인 | 기한: 내일(기준일 미확인) | 완료 기준: 전달 확인 | 조건: 보안 승인 후`,
  )
  const [action] = sections[0].actions
  // 이름표가 없는 조각은 버리지 않고 할 일로 이어 붙입니다.
  assert.equal(action.task, '요청 · 보안 체크리스트 전달')
  assert.deepEqual(
    action.fields.map((field) => field.label),
    ['담당', '기한', '완료 기준', '조건'],
  )
  assert.equal(action.fields[1].value, '내일(기준일 미확인)')
})

test('이름표가 줄마다 따로 와도 조치 하나로 접힌다', () => {
  // 지침은 한 줄에 ' · ' 로 쓰라고 하지만 실제 출력은 항목마다 줄을 나눕니다.
  const sections = reportSections(`**후속 조치**

- 합의된 후속: 시즌별 상담 시나리오와 패키지 초안 공유
- 담당자: 담당 미지정
- 기한: 미확인
- 완료 기준: 자료 전달 후 담당자의 검토 의견 또는 추가 질문 확인
- 필요사항·제안: 다음 방문 전까지 담당자별 질문 정리
- 담당자: 담당 미지정
- 이행 여부: 미확인`)

  const { actions } = sections[0]
  assert.equal(actions.length, 2)

  assert.equal(actions[0].task, '합의된 후속: 시즌별 상담 시나리오와 패키지 초안 공유')
  assert.deepEqual(actions[0].fields, [
    { label: '담당자', value: '담당 미지정' },
    { label: '기한', value: '미확인' },
    { label: '완료 기준', value: '자료 전달 후 담당자의 검토 의견 또는 추가 질문 확인' },
  ])

  // 값 안에 붙어 있는 가운뎃점은 여전히 구분자가 아닙니다.
  assert.equal(actions[1].task, '필요사항·제안: 다음 방문 전까지 담당자별 질문 정리')
  assert.deepEqual(
    actions[1].fields.map((field) => field.label),
    ['담당자', '이행 여부'],
  )
})

test('일일 보고서의 줄표·쉼표 꼴도 같은 카드로 읽힌다', () => {
  // daily-report-writer 출력. 딜 보고서와 달리 ' · ' 가 아니라 '— …, …' 로 옵니다.
  const sections = reportSections(`**다음 업무**

- 공식 제품 자료 제공 — 담당 미지정, 기한 미확인, 완료 기준 미확인
- 교육 담당자 미팅 연결 — 담당 미지정, 기한 미확인, 완료 기준: 교육 담당자 미팅 연결
- 설치 조건, 기존 장비와의 역할 분담, 병원 동선 및 장비 역할의 중복·보완 여부 확인 — 담당 미지정, 기한 미확인, 완료 기준: 관련 조건 확인`)

  const { actions } = sections[0]
  assert.equal(actions.length, 3)

  // 콜론 없는 빈 값도 이름표로 갈립니다.
  assert.equal(actions[0].task, '공식 제품 자료 제공')
  assert.deepEqual(actions[0].fields, [
    { label: '담당', value: '미지정' },
    { label: '기한', value: '미확인' },
    { label: '완료 기준', value: '미확인' },
  ])

  assert.equal(actions[1].fields[2].value, '교육 담당자 미팅 연결')

  // 할 일 안의 쉼표와 가운뎃점은 구분자가 아닙니다 — 조각나면 안 됩니다.
  assert.equal(
    actions[2].task,
    '설치 조건, 기존 장비와의 역할 분담, 병원 동선 및 장비 역할의 중복·보완 여부 확인',
  )
  assert.equal(actions[2].fields.length, 3)
})

test('아는 꼴이 아니면 null 을 내어 원문을 그대로 그리게 한다', () => {
  // 미팅 공통·미지정 기록 — 소제목 없는 평평한 목록입니다.
  assert.equal(
    reportSections(`- 기존 시스템 데이터 이전 기간에 대한 우려가 있습니다.
- 다음 공통 점검 회의는 9월 18일 오전 10시에 진행합니다.`),
    null,
  )
  // 서버 sentinel — 근거 없는 딜의 본문입니다.
  assert.equal(reportSections('이번 미팅에서 구체적 논의 없음'), null)
  // 소제목 형식 이전의 옛 줄글 보고서.
  assert.equal(
    reportSections('미팅 목적과 활동 방식은 미확인입니다. 견적을 전달했습니다.'),
    null,
  )
  assert.equal(reportSections(''), null)
  assert.equal(reportSections('   \n  '), null)
})

test('이름표가 하나도 없는 목록은 후속 조치로 바꾸지 않는다', () => {
  const sections = reportSections(`**논의 내용**

- 원리와 자료 출처를 반복해 확인했습니다.
- 학술 활동과 교육 자료 확인을 중요하게 여긴다고 설명했습니다.`)
  // 목록이지만 담당·기한이 없습니다. 평범한 목록으로 두어야 카드로 부풀지 않습니다.
  assert.equal(sections[0].actions, undefined)
  assert.match(sections[0].body, /^- 원리와/)
})

test('잘린 스트림 조각도 깨지지 않고 구획이 하나씩 늘어난다', () => {
  const growing = [
    '**미팅 목적**',
    '**미팅 목적**\n\n재고관리 SaaS 도입 조건',
    '**미팅 목적**\n\n재고관리 SaaS 도입 조건을 확인했습니다.\n\n**논의 내용**\n\n견적을 전',
  ].map((partial) => reportSections(partial))

  // 소제목만 와도 자리를 잡아 둡니다 — 글이 도착할 때 구획이 튀지 않습니다.
  assert.deepEqual(growing[0].map((section) => section.heading), ['미팅 목적'])
  assert.equal(growing[0][0].body, '')
  assert.equal(growing[1][0].body, '재고관리 SaaS 도입 조건')
  assert.deepEqual(growing[2].map((section) => section.heading), ['미팅 목적', '논의 내용'])
  assert.equal(growing[2][1].body, '견적을 전')

  // 굵은 글씨가 열리기만 한 순간에도 본문이 사라지지 않습니다.
  assert.equal(reportSections('**미팅 목'), null)
})

test('첫 소제목 앞의 글은 버리지 않고 이름 없는 구획으로 남는다', () => {
  const sections = reportSections(`사람이 맨 앞에 덧붙인 문단입니다.

**미팅 목적**

견적 조건을 확인했습니다.`)
  assert.equal(sections.length, 2)
  assert.equal(sections[0].heading, '')
  assert.equal(sections[0].body, '사람이 맨 앞에 덧붙인 문단입니다.')
  assert.equal(sections[1].heading, '미팅 목적')
})
