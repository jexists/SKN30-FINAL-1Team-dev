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
  assert.equal(
    sections[0].body,
    '재고관리 SaaS 도입 조건을 확인하기 위해 한빛유통 최 팀장과 온라인 미팅을 진행했습니다.',
  )
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

test('줄표가 칸마다 반복되고 마지막 이름표가 빠져도 같은 카드가 된다', () => {
  // 실제 관측된 미팅 보고서 출력. 구분자가 ' — ' 이고 '완료 기준:' 이름표가 통째로 빠집니다.
  const sections = reportSections(`**후속 조치**

- 합의된 후속 조치: 견적 발송 후 검토 여부 확인 — 담당자: 판매자 — 기한: 다음 주 목요일 오후(기준일 미확인) — 고객의 검토 여부 확인
- 합의된 후속 조치: 견적 수신 확인 전 전화하지 않기 — 담당자: 판매자 — 기한: 다음 주 목요일 오후 — 해당 기간에는 전화하지 않고 다음 주 목요일 오후에 수신 확인 연락`)

  const { actions } = sections[0]
  assert.equal(actions.length, 2)

  // 제목에 접두사로 붙은 상태는 필드로 옮깁니다 — 가운뎃점 꼴의 '· 상태: 합의' 와 같은 정보입니다.
  assert.equal(actions[0].task, '견적 발송 후 검토 여부 확인')
  assert.deepEqual(actions[0].fields, [
    { label: '상태', value: '합의된 후속 조치' },
    { label: '담당자', value: '판매자' },
    { label: '기한', value: '다음 주 목요일 오후(기준일 미확인)' },
    // 이름표 없이 온 마지막 조각은 남은 칸인 완료 기준입니다.
    { label: '완료 기준', value: '고객의 검토 여부 확인' },
  ])

  assert.equal(actions[1].task, '견적 수신 확인 전 전화하지 않기')
  assert.equal(
    actions[1].fields[3].value,
    '해당 기간에는 전화하지 않고 다음 주 목요일 오후에 수신 확인 연락',
  )
})

test('가운뎃점 꼴은 이름표가 다 붙어 있어 그대로 같은 카드가 된다', () => {
  const sections = reportSections(`**후속 조치**

- 병원 상황에 맞는 2~3개 운영 시나리오 제안 · 담당: 담당 미지정 · 기한: 미확인 · 완료 기준: 후속 연락 결과와 다음 단계가 기록됨 · 상태: 합의
- 다음 협의에 필요한 자료 또는 일정 확인 · 담당: 담당 미지정 · 기한: 미확인 · 완료 기준: 미확인 · 상태: 고객 요청·합의 여부 미확인`)

  const { actions } = sections[0]
  assert.equal(actions[0].task, '병원 상황에 맞는 2~3개 운영 시나리오 제안')
  assert.deepEqual(
    actions[0].fields.map((field) => field.label),
    ['담당', '기한', '완료 기준', '상태'],
  )
  // 값 안에 붙어 있는 가운뎃점은 구분자가 아닙니다.
  assert.equal(actions[1].fields[3].value, '고객 요청·합의 여부 미확인')
})

test('줄표 뒤 이름표 없는 상태가 먼저 와도 카드로 읽힌다', () => {
  const sections = reportSections(`**다음 업무**

- 공식 제품 자료 제공 — 합의된 후속 조치, 담당 미지정, 기한 미확인, 완료 기준 미확인
- 의사결정자와의 다음 일정 확정 — 검토 필요, 담당 미지정, 기한 미확인, 완료 기준: 다음 일정 확정`)

  const { actions } = sections[0]
  assert.equal(actions[0].task, '공식 제품 자료 제공')
  assert.deepEqual(actions[0].fields, [
    { label: '상태', value: '합의된 후속 조치' },
    { label: '담당', value: '미지정' },
    { label: '기한', value: '미확인' },
    { label: '완료 기준', value: '미확인' },
  ])
  assert.equal(actions[1].task, '의사결정자와의 다음 일정 확정')
  assert.equal(actions[1].fields[0].value, '검토 필요')
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
  assert.equal(reportSections('미팅 목적과 활동 방식은 미확인입니다. 견적을 전달했습니다.'), null)
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
  assert.deepEqual(
    growing[0].map((section) => section.heading),
    ['미팅 목적'],
  )
  assert.equal(growing[0][0].body, '')
  assert.equal(growing[1][0].body, '재고관리 SaaS 도입 조건')
  assert.deepEqual(
    growing[2].map((section) => section.heading),
    ['미팅 목적', '논의 내용'],
  )
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

test('쌍반점으로 칸을 나눈 꼬리도 칸마다 갈린다', () => {
  const sections = reportSections(`**다음 업무**

- LR1000·LR2000 비교 견적 작성 및 원장님·실장님 전달 — 담당자: 미지정; 기한: 미확인; 완료 기준: 모델별 차이, 액세서리 및 추가 비용이 구분된 견적을 두 수신자에게 전달함
- 프로브 액세서리 처리 — 담당자: 미지정; 기한: 호환성 확인 시점 미확인; 선행조건: 기존 장비 모델 확인; 완료 기준: 선택 항목으로 견적에 표시함`)
  const [first, second] = sections[0].actions
  assert.equal(first.task, 'LR1000·LR2000 비교 견적 작성 및 원장님·실장님 전달')
  assert.deepEqual(first.fields, [
    { label: '담당자', value: '미지정' },
    { label: '기한', value: '미확인' },
    // 값 안의 쉼표는 이름표가 뒤따르지 않으므로 그대로 둡니다.
    {
      label: '완료 기준',
      value: '모델별 차이, 액세서리 및 추가 비용이 구분된 견적을 두 수신자에게 전달함',
    },
  ])
  assert.deepEqual(
    second.fields.map((field) => field.label),
    ['담당자', '기한', '선행조건', '완료 기준'],
  )
})

test('전달 방식도 자기 칸으로 선다', () => {
  // 이름표가 목록에 없으면 앞 칸 값에 통째로 딸려 들어갑니다 — 관측된 줄 그대로.
  const sections = reportSections(`**다음 업무**

- LR1000·LR2000 비교 견적 작성 및 전달 — 담당자: 미지정; 선행조건: 기존 장비 모델·설치 공간·필요 구성품 확인; 전달 방식: 실장 이메일로 보내고 원장님에게도 함께 보냄; 완료 기준: 두 수신자에게 전달함`)

  const [action] = sections[0].actions
  assert.deepEqual(action.fields, [
    { label: '담당자', value: '미지정' },
    { label: '선행조건', value: '기존 장비 모델·설치 공간·필요 구성품 확인' },
    { label: '전달 방식', value: '실장 이메일로 보내고 원장님에게도 함께 보냄' },
    { label: '완료 기준', value: '두 수신자에게 전달함' },
  ])
})

test('이름표 없는 조각을 상태로 지어내지 않는다', () => {
  // '담당자' 라는 말이 상태 배지로 올라가던 자리입니다. 상태 낱말이 아니면
  // 정해진 칸 순서로만 채우고, 배지가 될 상태 필드는 만들지 않습니다.
  const sections = reportSections(`**다음 업무**

- LR1000·LR2000 비교 견적 작성 및 원장님·실장님 전달 — 담당자 · 기한 미확인`)
  const [action] = sections[0].actions
  assert.equal(action.task, 'LR1000·LR2000 비교 견적 작성 및 원장님·실장님 전달')
  assert.equal(
    action.fields.some((field) => field.label === '상태'),
    false,
  )
})

test('상태 낱말로 온 조각은 그대로 상태가 된다', () => {
  const sections = reportSections(`**후속 조치**

- 견적 요청 — 요청·수락 여부 미확인, 담당 미지정`)
  const [action] = sections[0].actions
  assert.deepEqual(action.fields, [
    { label: '상태', value: '요청·수락 여부 미확인' },
    { label: '담당', value: '미지정' },
  ])
})

test('report-style 이 정한 꼴 그대로 칸이 갈린다', () => {
  // backend/app/agents/reports/skills/report-style/SKILL.md 의 예시 세 줄입니다.
  const sections = reportSections(`**다음 업무**

- **LR1000·LR2000 비교 견적 작성 및 원장님·실장님 전달** · 담당자: 본인 · 기한: 미확인 · 전달 방식: 실장 이메일·원장 동시 수신 · 상태: 요청
- **기존 장비 모델·설치 공간·필요 구성품 확인** · 담당자: 미지정 · 기한: 미확인 · 선행조건: 고객 회신
- **견적 수신·검토 여부 확인** · 담당자: 본인 · 기한: 다음 주 목요일 오후·연도 미확인 · 조건: 목요일 오후 전에는 전화하지 않음`)
  const [first, second, third] = sections[0].actions
  assert.equal(first.task, 'LR1000·LR2000 비교 견적 작성 및 원장님·실장님 전달')
  assert.deepEqual(first.fields, [
    { label: '담당자', value: '본인' },
    { label: '기한', value: '미확인' },
    { label: '전달 방식', value: '실장 이메일·원장 동시 수신' },
    { label: '상태', value: '요청' },
  ])
  assert.deepEqual(second.fields.at(-1), { label: '선행조건', value: '고객 회신' })
  assert.equal(third.task, '견적 수신·검토 여부 확인')
  assert.deepEqual(third.fields.at(-1), {
    label: '조건',
    value: '목요일 오후 전에는 전화하지 않음',
  })
})

test('이름표 여럿이 한 값을 나눠 쓰고 뒤에 설명이 붙은 꼴도 칸마다 갈린다', () => {
  // 실제로 관측된 다음 업무입니다. '담당자·기한 미확인' 에서 붙어 있는 가운뎃점을 자르면
  // 이름표만 남은 '담당자' 가 담당자 칸의 값이 되고, 나머지가 통째로 기한에 밀려 들어갑니다.
  const sections = reportSections(`**다음 업무**

- LR1000·LR2000 비교 견적 작성 및 원장님·실장님 전달 — 담당자·기한 미확인; 실장 이메일로 보내고 원장님에게도 함께 전달
- 견적 수신 및 검토 여부 확인 — 다음 주 목요일 오후; 정확한 연도 및 기준일은 미확인; 목요일 오후 전에는 전화하지 않음`)
  const [first, second] = sections[0].actions

  assert.equal(first.task, 'LR1000·LR2000 비교 견적 작성 및 원장님·실장님 전달')
  assert.deepEqual(first.fields, [
    { label: '담당자', value: '미확인' },
    { label: '기한', value: '미확인' },
    { label: '완료 기준', value: '실장 이메일로 보내고 원장님에게도 함께 전달' },
  ])

  // 이름표가 하나도 없는 꼬리는 칸 이름을 지어내지 않고 비고로 답니다.
  assert.equal(second.task, '견적 수신 및 검토 여부 확인')
  assert.deepEqual(second.fields, [
    {
      label: '비고',
      value:
        '다음 주 목요일 오후; 정확한 연도 및 기준일은 미확인; 목요일 오후 전에는 전화하지 않음',
    },
  ])
})

test('쌍점으로 칸을 열고 이름표가 도중에 끊기는 꼴도 카드가 된다', () => {
  // 실제로 관측된 후속 조치입니다. 할 일과 칸을 줄표가 아니라 쌍점이 가르고, 이름표는
  // 담당·기한까지만 붙은 뒤 완료 기준이 이름표 없이 줄글로 이어집니다.
  const sections = reportSections(`**후속 조치**

- 비교 견적 발송: 담당 미지정, 기한 미확인, 실장님 이메일로 발송하고 원장님에게도 동시 전달하는 것을 완료 기준으로 함.
- 견적 수신 및 검토 여부 확인 연락: 담당 미지정, 다음 주 목요일 오후, 견적 수신 확인만 짧게 연락하며 그 전에는 전화하지 않는 것을 완료 기준으로 함.
- 견적 비교 검토: 원장님 및 실장님, 다음 주 중 검토 예정, 구매 여부 판단은 미확인임.`)
  const [first, second, third] = sections[0].actions

  assert.equal(first.task, '비교 견적 발송')
  assert.deepEqual(first.fields, [
    { label: '담당', value: '미지정' },
    { label: '기한', value: '미확인' },
    {
      label: '완료 기준',
      value: '실장님 이메일로 발송하고 원장님에게도 동시 전달하는 것을 완료 기준으로 함',
    },
  ])

  // 이름표 없는 값도 지시문이 정한 칸 순서대로 들어갑니다.
  assert.equal(second.task, '견적 수신 및 검토 여부 확인 연락')
  assert.deepEqual(second.fields.at(1), { label: '기한', value: '다음 주 목요일 오후' })

  // 이름표가 하나도 없으면 칸 이름을 지어내지 않고 비고로 답니다.
  assert.equal(third.task, '견적 비교 검토')
  assert.deepEqual(third.fields, [
    {
      label: '비고',
      value: '원장님 및 실장님, 다음 주 중 검토 예정, 구매 여부 판단은 미확인임',
    },
  ])
})

test('값 안의 쉼표에서 조각나도 마지막 칸에 그대로 이어 붙는다', () => {
  const sections = reportSections(`**후속 조치**

- 비교 견적 작성: 담당 미지정, 기한 미확인, 기본안·확장 검토안을 판매자가 제안했으며, 모델별 사양 차이를 기재하는 것을 완료 기준으로 함.`)
  assert.deepEqual(sections[0].actions[0].fields.at(-1), {
    label: '완료 기준',
    value:
      '기본안·확장 검토안을 판매자가 제안했으며, 모델별 사양 차이를 기재하는 것을 완료 기준으로 함',
  })
})

test('지침에 없는 이름표는 상태 배지가 아니라 제 이름의 한 줄이 된다', () => {
  // '요청·진행 주체: …' 는 요청으로 시작한다는 이유만으로 상태가 되어 파란 배지로 올라갔습니다.
  // 쌍점을 달고 온 조각은 상태가 아니라 제 이름표를 가진 칸입니다.
  const sections = reportSections(`**후속 조치**

- LR1000·LR2000 비교 견적 작성 및 발송 — 담당자: 판매자, 기한: 미확인, 요청·진행 주체: 고객이 요청했고 판매자가 발송하기로 함`)
  const [action] = sections[0].actions
  assert.equal(
    action.fields.some((field) => field.label === '상태'),
    false,
  )
  assert.deepEqual(action.fields.at(-1), {
    label: '요청·진행 주체',
    value: '고객이 요청했고 판매자가 발송하기로 함',
  })
})

test("'할 일:' 로 열고 마침표로 칸을 나누는 꼴도 카드가 된다", () => {
  // 실제로 관측된 후속 조치입니다. 구분자가 마침표이고 할 일마저 이름표를 답니다.
  // 구분자를 쫓지 않고 이름표 자리를 기준으로 가르므로 이 꼴도 같은 카드가 됩니다.
  const sections = reportSections(`**후속 조치**

- 할 일: LR1000·LR2000 비교 견적 발송. 담당자: 견적 발언자(영업담당자). 기한: 미확인. 완료 기준: 원장님과 실장님이 수신할 수 있도록 함께 발송.
- 할 일: 모델별 가격 차이, 실제 사양, 포함·제외 구성을 견적서에 기재. 담당자: 견적 발언자(영업담당자). 기한: 미확인.
- 고객 측 검토: 원장님과 실장님이 다른 장비 견적과 비교. 담당자: 실장 및 원장님. 완료 기준: 미확인.`)
  const [first, second, third] = sections[0].actions

  assert.equal(first.task, 'LR1000·LR2000 비교 견적 발송')
  assert.deepEqual(first.fields, [
    { label: '담당자', value: '견적 발언자(영업담당자)' },
    { label: '기한', value: '미확인' },
    { label: '완료 기준', value: '원장님과 실장님이 수신할 수 있도록 함께 발송' },
  ])

  // 할 일 안의 쉼표는 구분자가 아닙니다. 이름표 자리에서만 가릅니다.
  assert.equal(second.task, '모델별 가격 차이, 실제 사양, 포함·제외 구성을 견적서에 기재')

  // 줄 맨 앞의 모르는 이름표는 칸이 아니라 제목입니다.
  assert.equal(third.task, '고객 측 검토')
  assert.deepEqual(third.fields[0], {
    label: '비고',
    value: '원장님과 실장님이 다른 장비 견적과 비교',
  })
})
