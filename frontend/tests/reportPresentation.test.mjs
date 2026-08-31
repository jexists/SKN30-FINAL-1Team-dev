import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

// 기존 Vite 변환으로 실제 TS/TSX를 읽는다. HTTP 서버나 업무 API는 호출하지 않는다.
const vite = await createServer({
  server: { middlewareMode: true, hmr: false },
  define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('http://synthetic.invalid') },
})
after(() => vite.close())
const { sourcesFor } = await vite.ssrLoadModule('/src/pages/Daily/sources.ts')
const { fromMeetingReport } = await vite.ssrLoadModule('/src/pages/Daily/rows.ts')
const { toMeetingReport } = await vite.ssrLoadModule('/src/pages/Meetings/useMeetingReports.ts')
const { default: MeetingSharedPanel } = await vite.ssrLoadModule(
  '/src/pages/Meetings/components/MeetingSharedPanel.tsx',
)

const dealId = '10000000-0000-4000-8000-000000000001'
const response = (values = {}, fields = []) => ({
  id: 'synthetic-report',
  author_member_id: 'synthetic-author',
  author_display_name: '합성 작성자',
  source_activity_id: 'synthetic-meeting',
  sales_deal_id: dealId,
  report_date: '2026-08-31',
  status_code: 'approved',
  template_snapshot: { id: 'synthetic-template', fields },
  content: { values, title: '합성 보고서' },
})
const ledger = () => ({
  schema_version: 'meeting_content.v1',
  transcript_sha256: 'a'.repeat(64),
  selected_deal_ids: [dealId],
  items: [
    {
      segment: { segment_id: 'S0001', start: 0, end: 5, text: '합성 원문' },
      applicability: { scope: 'unresolved', deal_ids: [] },
    },
  ],
})
const convertLedger = (evidence) =>
  toMeetingReport({ ...response(), source_snapshot: { evidence } }).evidenceLedger

test('일정 연결·독립 미팅 자료 모두 설명 첫 줄의 공백과 CRLF를 제거한다', () => {
  const cases = [
    [{ body: '  본문 첫 줄  \r\n둘째 줄', decision: '낮은 우선순위' }, '본문 첫 줄'],
    [{ decision: ' 결정 사항 \r\n둘째 줄' }, '결정 사항'],
    [{ note: '\t메모 첫 줄\t\r\n둘째 줄' }, '메모 첫 줄'],
    [{ body: ' \t\r\n둘째 줄' }, '미팅 기록 확정'],
    [{ body: '', decision: '', note: '  ' }, '미팅 기록 확정'],
    [{}, '미팅 기록 확정'],
  ]
  for (const [values, expected] of cases) {
    const report = toMeetingReport(response(values))
    for (const agenda of [[], [{ id: report.agendaId, date: report.date }]]) {
      const result = sourcesFor('일일', report.date, [report], [], agenda)
      assert.equal(result.activities.length, 1)
      assert.equal(result.activities[0].desc, expected)
      assert.equal(result.values.get(`meet-${report.id}`), report.values)
    }
  }
})

test('미팅 목록 요약은 저장 양식 순서와 비어 있지 않은 값을 먼저 사용한다', () => {
  const field = (id) => ({ id, label: id, type: 'textarea' })
  const report = toMeetingReport(
    response({ custom: '  저장 양식 본문  ', body: '기본 본문', second: '둘째 항목' }, [
      field('custom'),
      field('second'),
    ]),
  )
  assert.equal(fromMeetingReport(report).summary, '저장 양식 본문')
  report.values.custom = '  '
  assert.equal(fromMeetingReport(report).summary, '둘째 항목')
  report.values.second = '\t'
  assert.equal(fromMeetingReport(report).summary, '기본 본문')
  report.values.body = ''
  report.values.reaction = '  고객 반응  '
  assert.equal(fromMeetingReport(report).summary, '고객 반응')
  report.values.reaction = ''
  report.values.note = ' 메모 '
  assert.equal(fromMeetingReport(report).summary, '메모')
  report.values.note = ''
  assert.equal(fromMeetingReport(report).summary, '')
})

test('저장 근거는 모든 scope의 중첩 구조가 정상이면 원본 변경 없이 복원한다', () => {
  const scopes = [
    'meeting_context',
    'company_context',
    'all_selected_deals',
    'deal',
    'unresolved',
    'out_of_scope',
  ]
  for (const scope of scopes) {
    const evidence = ledger()
    evidence.items[0].applicability = { scope, deal_ids: scope === 'deal' ? [dealId] : [] }
    const before = JSON.stringify(evidence)
    assert.equal(convertLedger(evidence), evidence)
    assert.equal(JSON.stringify(evidence), before)
  }
})

test('손상된 저장 근거는 부분 복원하지 않고 undefined로 제외해 화면 충돌을 막는다', () => {
  const mutations = [
    (v) => {
      v.schema_version = 'meeting_content.v2'
    },
    (v) => {
      v.transcript_sha256 = null
    },
    (v) => {
      v.transcript_sha256 = 'bad-hash'
    },
    (v) => {
      v.selected_deal_ids = []
    },
    (v) => {
      v.selected_deal_ids = [null]
    },
    (v) => {
      v.selected_deal_ids.push(dealId)
    },
    (v) => {
      v.items = [null]
    },
    (v) => {
      v.items = []
    },
    (v) => {
      v.items.push({})
    },
    (v) => {
      v.items[0].segment = null
    },
    (v) => {
      v.items[0].segment.segment_id = 'not-a-segment'
    },
    (v) => {
      v.items[0].segment.start = -1
    },
    (v) => {
      v.items[0].segment.start = '0'
    },
    (v) => {
      v.items[0].segment.end = 0
    },
    (v) => {
      v.items[0].segment.end = Number.NaN
    },
    (v) => {
      v.items[0].segment.text = null
    },
    (v) => {
      v.items[0].applicability = null
    },
    (v) => {
      v.items[0].applicability.scope = 'unknown-scope'
    },
    (v) => {
      v.items[0].applicability.deal_ids = null
    },
    (v) => {
      v.items[0].applicability = { scope: 'deal', deal_ids: [null] }
    },
    (v) => {
      v.items[0].applicability = { scope: 'deal', deal_ids: [] }
    },
    (v) => {
      v.items[0].applicability = { scope: 'deal', deal_ids: ['another-deal'] }
    },
    (v) => {
      v.items[0].applicability = { scope: 'deal', deal_ids: [dealId, dealId] }
    },
    (v) => {
      v.items[0].applicability.deal_ids = [dealId]
    },
    (v) => {
      v.items.push(structuredClone(v.items[0]))
    },
  ]
  for (const change of mutations) {
    const evidence = ledger()
    change(evidence)
    assert.equal(convertLedger(evidence), undefined, change.toString())
  }
  assert.equal(convertLedger(null), undefined)
  assert.equal(convertLedger({ items: [null], selected_deal_ids: [] }), undefined)
  assert.doesNotThrow(() =>
    renderToStaticMarkup(
      createElement(MeetingSharedPanel, {
        shared: null,
        evidence: convertLedger({ items: [null], selected_deal_ids: [] }),
      }),
    ),
  )
})

test('공통·미지정 기록은 읽기 전용 제목과 편집용 연결 label을 구분한다', () => {
  const shared = {
    run_id: 'synthetic-run',
    revision: 'synthetic-revision',
    common_report: { body: '공통 내용 본문', evidence_ids: [] },
    unassigned_report: { body: '미지정 내용 본문', evidence_ids: [] },
  }
  const view = renderToStaticMarkup(createElement(MeetingSharedPanel, { shared }))
  assert.match(view, /<h3[^>]*>공통 내용<\/h3>/)
  assert.match(view, /<h3[^>]*>딜 미지정 · 확인 필요<\/h3>/)
  assert.doesNotMatch(view, /<label|<textarea/)
  assert.match(view, /공통 내용 본문/)
  assert.match(view, /미지정 내용 본문/)
  const edit = renderToStaticMarkup(createElement(MeetingSharedPanel, { shared, onSave() {} }))
  const labels = [...edit.matchAll(/<label for="([^"]+)">/g)]
  assert.equal(labels.length, 2)
  for (const [, id] of labels) assert(edit.includes(`<textarea id="${id}"`))
})
