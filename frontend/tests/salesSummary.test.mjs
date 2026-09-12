import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const vite = await createServer({
  server: { middlewareMode: true, hmr: false },
  define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('http://synthetic.invalid') },
})
after(() => vite.close())

const { salesSummaryOf } = await vite.ssrLoadModule('/src/pages/Sales/useSalesSummary.ts')
const { TODAY_ISO } = await vite.ssrLoadModule('/src/utils/date.ts')
const { default: RevenuePanel } = await vite.ssrLoadModule(
  '/src/pages/Sales/components/RevenuePanel/RevenuePanel.tsx',
)
const { client } = await vite.ssrLoadModule('/src/api/client.ts')

client.defaults.adapter = async (config) => ({
  data: [],
  status: 200,
  statusText: 'OK',
  headers: {},
  config,
})

const deals = [
  {
    org: '가람병원',
    region: '서울',
    product: 'A 제품',
    owner: '김영업',
    ownerMemberId: 'kim',
    status: '확정',
    amount: 900,
    contractAmount: 100,
    contractNo: 'C-1',
    stagePhase: 'contract',
    date: TODAY_ISO,
  },
  {
    org: '가람병원',
    region: '서울',
    product: 'B 제품',
    owner: '이영업',
    ownerMemberId: 'lee',
    status: '확정',
    amount: 720,
    contractAmount: 80,
    contractNo: 'C-2',
    stagePhase: 'contract',
    date: TODAY_ISO,
  },
  {
    org: '누리병원',
    region: '경기',
    product: 'A 제품',
    owner: '김영업',
    ownerMemberId: 'kim',
    status: '확정',
    amount: 360,
    contractAmount: 40,
    contractNo: 'C-3',
    stagePhase: 'contract',
    date: TODAY_ISO,
  },
]

// 매출은 예상금액(amount)이 아니라 계약금액(contractAmount)으로 셉니다. 두 값을 일부러
// 다르게 두어 어느 쪽을 세는지 아래 기대값이 드러내게 합니다.
function group(summary, key) {
  const found = summary.groups.find((item) => item.key === key)
  assert.ok(found, `${key} 그룹이 있어야 합니다.`)
  return found
}

test('매출은 예상금액이 아니라 계약금액으로 센다', () => {
  const summary = salesSummaryOf(deals, 'month', 0, 'org')

  // 예상금액 합계(900+720+360=1980)가 아니라 계약금액 합계입니다.
  assert.equal(summary.totals.actual, 220)
})

test('계약금액을 아직 적지 않은 확정 딜은 0으로 센다', () => {
  const blank = {
    org: '한빛병원',
    region: '서울',
    product: 'A 제품',
    owner: '김영업',
    ownerMemberId: 'kim',
    status: '확정',
    amount: 500,
    contractAmount: null,
    contractNo: 'C-4',
    stagePhase: 'contract',
    date: TODAY_ISO,
  }
  const selected = group(salesSummaryOf([...deals, blank], 'month', 0, 'org'), '한빛병원')

  assert.equal(selected.actual, 0)
  // 금액은 0이어도 목록에 서는 줄이라 건수는 셉니다.
  assert.equal(selected.contracts.length, 1)
  assert.deepEqual(
    selected.owners.map(({ memberId, actual, count }) => ({ memberId, actual, count })),
    [{ memberId: 'kim', actual: 0, count: 1 }],
  )
})

test('회사별 선택 항목은 그 회사의 담당자별 매출·계약 건수만 집계한다', () => {
  const selected = group(salesSummaryOf(deals, 'month', 0, 'org'), '가람병원')

  assert.equal(selected.actual, 180)
  assert.equal(selected.contracts.length, 2)
  assert.deepEqual(selected.owners, [
    { memberId: 'kim', name: '김영업', actual: 100, count: 1 },
    { memberId: 'lee', name: '이영업', actual: 80, count: 1 },
  ])
})

test('지역별과 상품별도 같은 담당자 분해 규칙을 쓴다', () => {
  const seoul = group(salesSummaryOf(deals, 'month', 0, 'region'), '서울')
  const productA = group(salesSummaryOf(deals, 'month', 0, 'product'), 'A 제품')

  assert.deepEqual(seoul.owners.map(({ memberId, actual, count }) => ({ memberId, actual, count })), [
    { memberId: 'kim', actual: 100, count: 1 },
    { memberId: 'lee', actual: 80, count: 1 },
  ])
  assert.deepEqual(productA.owners.map(({ memberId, actual, count }) => ({ memberId, actual, count })), [
    { memberId: 'kim', actual: 140, count: 2 },
  ])
})

test('전체 차트를 유지한 채 선택한 그룹의 담당자 구성을 아래에 덧붙인다', () => {
  const summary = salesSummaryOf(deals, 'month', 0, 'org')
  const selectedGroup = group(summary, '가람병원')
  const view = renderToStaticMarkup(
    createElement(RevenuePanel, {
      range: { label: '이번 달', fromISO: TODAY_ISO, toISO: TODAY_ISO, sub: '' },
      summary,
      by: 'org',
      selectedGroup,
      onSelectGroup() {},
      trend: [
        {
          offset: 0,
          label: '이번 달',
          short: '이번 달',
          actual: summary.totals.actual,
          isCurrent: true,
        },
      ],
      trendCaption: '매출 추이',
    }),
  )

  assert.match(view, /이번 달 · 회사별/)
  assert.match(view, /가람병원 매출 구성/)
  assert.match(view, /상세 닫기/)
  assert.match(view, /담당자 2명/)
  assert.match(view, /김영업/)
  assert.match(view, /계약 1건/)
  assert.match(view, /매출 추이/)
})
