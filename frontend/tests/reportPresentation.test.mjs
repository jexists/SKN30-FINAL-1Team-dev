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
const { meetingLinkFor, sourcesFor } = await vite.ssrLoadModule('/src/pages/Daily/sources.ts')
const { fromMeetingReport } = await vite.ssrLoadModule('/src/pages/Daily/rows.ts')
const { historyQueryScopes } = await vite.ssrLoadModule('/src/pages/Daily/useReportHistory.ts')
const { meetingRequestOf, toMeetingReport } = await vite.ssrLoadModule(
  '/src/pages/Meetings/useMeetingReports.ts',
)
const { canEditPeriodReport, detailTemplateOf, ownPeriodReportQuery, toReport } =
  await vite.ssrLoadModule('/src/pages/Daily/useDailyReports.ts')
const { default: ReportFields } = await vite.ssrLoadModule(
  '/src/components/ReportFields/ReportFields.tsx',
)
const { initScope, resetScope } = await vite.ssrLoadModule('/src/shared/scope.ts')
const { default: MeetingSharedPanel } = await vite.ssrLoadModule(
  '/src/pages/Meetings/components/MeetingSharedPanel.tsx',
)
const { ReportReviewContents } = await vite.ssrLoadModule(
  '/src/pages/Dashboard/components/ReportReviewDrawer/ReportReviewDrawer.tsx',
)
const { reviewReport } = await vite.ssrLoadModule('/src/shared/reviewDecision.ts')
const { client } = await vite.ssrLoadModule('/src/api/client.ts')

const dealId = '10000000-0000-4000-8000-000000000001'
const dealSection = (values = {}, id = dealId) => ({
  sales_deal_id: id,
  deal_snapshot: { id, label: id === dealId ? 'DEAL-1' : 'DEAL-2' },
  content: { product: '합성 제품', title: '합성 딜 보고서', values },
  ai_evidence: null,
  created_at: '2026-08-31T10:00:00Z',
  updated_at: '2026-08-31T10:00:00Z',
})
const response = (values = {}, fields = [], dealSections = [dealSection(values)]) => ({
  id: 'synthetic-report',
  author_member_id: 'synthetic-author',
  author_display_name: '합성 작성자',
  source_activity_id: 'synthetic-meeting',
  sales_deal_id: null,
  report_date: '2026-08-31',
  status_code: 'approved',
  template_snapshot: { id: 'synthetic-template', fields },
  content: { title: '합성 보고서' },
  deal_sections: dealSections,
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

const periodResponse = ({
  body = null,
  structuredValues = {},
  status = 'draft',
  reviewNote = null,
} = {}) => ({
  id: 'synthetic-period-report',
  author_member_id: 'synthetic-author',
  author_display_name: '합성 작성자',
  recipient_display_name: '합성 팀장',
  report_kind: 'daily',
  report_date: '2026-08-31',
  period_start: null,
  period_end: null,
  status_code: status,
  version: 1,
  current_submission_id: null,
  template_snapshot: {
    id: 'legacy-daily',
    fields: [{ id: 'summary', label: '요약', type: 'textarea' }],
  },
  content: {},
  body,
  structured_values: structuredValues,
  transcript: null,
  note: null,
  review_note: reviewNote,
  activities: [],
})

test('기간 보고서 상세는 구조화 요약과 별도 본문을 함께 보이고 같은 본문은 중복하지 않는다', () => {
  const report = toReport(
    periodResponse({ body: '실제 canonical 본문', structuredValues: { summary: '기존 요약' } }),
  )
  const view = renderToStaticMarkup(
    createElement(ReportFields, {
      template: detailTemplateOf(report),
      values: report.values,
      readOnly: true,
    }),
  )
  assert.match(view, /기존 요약/)
  assert.match(view, /실제 canonical 본문/)

  const duplicated = toReport(
    periodResponse({ body: '같은 내용', structuredValues: { summary: '같은 내용' } }),
  )
  assert.deepEqual(
    detailTemplateOf(duplicated).fields.map((field) => field.id),
    ['summary'],
  )
})

test('기간 보고서 상세의 수정 진입은 본인 draft와 changes_requested에만 열린다', () => {
  const draft = toReport(periodResponse({ status: 'draft' }))
  const returned = toReport(
    periodResponse({ status: 'changes_requested', reviewNote: '수치를 보완해 주세요.' }),
  )

  assert.equal(canEditPeriodReport(draft, 'synthetic-author'), true)
  assert.equal(canEditPeriodReport(returned, 'synthetic-author'), true)
  assert.equal(canEditPeriodReport(draft, 'another-member'), false)
  assert.equal(
    canEditPeriodReport(toReport(periodResponse({ status: 'submitted' })), 'synthetic-author'),
    false,
  )
  assert.equal(returned.reviewNote, '수치를 보완해 주세요.')
})

test('팀장의 기간 보고서 작성 조회는 전역 팀 범위와 무관하게 본인으로 좁힌다', () => {
  initScope('manager-member', true)
  try {
    assert.deepEqual(ownPeriodReportQuery('주간', '2026-08-31').author_member_id, [
      'manager-member',
    ])
  } finally {
    resetScope()
  }
})

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
      assert.match(result.values.get(`meet-${report.id}`).body, /DEAL-1/)
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
  const values = report.dealSections[0].values
  values.custom = '  '
  assert.equal(fromMeetingReport(report).summary, '둘째 항목')
  values.second = '\t'
  assert.equal(fromMeetingReport(report).summary, '기본 본문')
  values.body = ''
  values.reaction = '  고객 반응  '
  assert.equal(fromMeetingReport(report).summary, '고객 반응')
  values.reaction = ''
  values.note = ' 메모 '
  assert.equal(fromMeetingReport(report).summary, '메모')
  values.note = ''
  assert.equal(fromMeetingReport(report).summary, '')
})

test('미팅 응답 한 건에서 공통 기록과 모든 딜 섹션을 분리해 복원한다', () => {
  const secondId = '10000000-0000-4000-8000-000000000002'
  const sections = [
    dealSection({ body: '첫 번째 딜 본문' }),
    {
      ...dealSection({ body: '두 번째 딜 본문' }, secondId),
      ai_evidence: {
        meeting_run_id: 'synthetic-run',
        deal_assessment: {
          label: 'high',
          high_probability: 0.82,
          model_version: 'synthetic-v1',
        },
      },
    },
  ]
  const report = toMeetingReport(response({}, [{ id: 'body', label: '본문' }], sections))

  assert.equal(report.title, '합성 보고서')
  assert.equal(report.dealSections.length, 2)
  assert.equal(report.dealSections[0].values.body, '첫 번째 딜 본문')
  assert.equal(report.dealSections[1].assessment.label, 'high')
  const sources = sourcesFor('일일', report.date, [report], [], [])
  assert.equal(sources.activities.length, 1)
  assert.match(sources.values.get(`meet-${report.id}`).body, /첫 번째 딜 본문/)
  assert.match(sources.values.get(`meet-${report.id}`).body, /두 번째 딜 본문/)
})

test('팀장 검토 화면은 공통·미지정 기록과 모든 딜 본문을 함께 표시한다', () => {
  const secondId = '10000000-0000-4000-8000-000000000002'
  const raw = response(
    {},
    [{ id: 'body', label: '본문' }],
    [
      dealSection({ body: '첫 딜 검토 본문' }),
      dealSection({ body: '둘째 딜 검토 본문' }, secondId),
    ],
  )
  raw.content.meeting_shared = {
    run_id: 'synthetic-run',
    revision: 'synthetic-revision',
    common_report: { body: '검토할 공통 기록', evidence_ids: [] },
    unassigned_report: { body: '검토할 미지정 기록', evidence_ids: [] },
  }

  const report = toMeetingReport(raw)
  const view = renderToStaticMarkup(createElement(ReportReviewContents, { report }))

  assert.match(view, /검토할 공통 기록/)
  assert.match(view, /검토할 미지정 기록/)
  assert.match(view, /DEAL-1/)
  assert.match(view, /DEAL-2/)
  assert.match(view, /첫 딜 검토 본문/)
  assert.match(view, /둘째 딜 검토 본문/)
})

test('미팅 공통·미지정 기록은 목록 검색과 일일보고 자료 설명에도 포함한다', () => {
  const raw = response({})
  raw.content.meeting_shared = {
    run_id: 'synthetic-run',
    revision: 'synthetic-revision',
    common_report: { body: '공통 검색 전용 문구', evidence_ids: [] },
    unassigned_report: { body: '미지정 설명 첫 줄\n둘째 줄', evidence_ids: [] },
  }
  const report = toMeetingReport(raw)
  const row = fromMeetingReport(report)

  assert.match(row.haystack, /공통 검색 전용 문구/)
  assert.match(row.haystack, /미지정 설명 첫 줄/)

  report.meetingShared.common_report = null
  const sources = sourcesFor('일일', report.date, [report], [], [])
  assert.equal(sources.activities[0].desc, '미지정 설명 첫 줄')
})

test('미팅 저장 요청은 한 report에 딜 섹션을 묶고 서버 소유 AI 필드를 보내지 않는다', () => {
  const request = meetingRequestOf({
    agendaId: 'synthetic-meeting',
    date: '2026-08-31',
    template: { id: 'template-1', name: '합성 양식', owner: '합성', updated: '', fields: [] },
    time: '10:00',
    hospital: '합성 고객사',
    dept: '구매팀',
    contact: '합성 담당자',
    place: '회의실',
    title: '미팅 대표 제목',
    transcript: '합성 원문',
    attachments: [],
    dealSections: [
      {
        salesDealId: dealId,
        salesDeal: { id: dealId, label: 'DEAL-1' },
        product: '제품 1',
        title: '딜 1 제목',
        values: { body: '딜 1 본문' },
        evidence: '근거 1',
        aiValues: { body: '보내면 안 되는 AI 초안' },
        aiEvidence: '보내면 안 되는 AI 근거',
        aiGeneratedAt: '2026-08-31T10:00:00Z',
        analysisEvidence: { meeting_run_id: '보내면 안 되는 실행 ID' },
      },
    ],
  })

  assert.equal(request.sales_deal_id, null)
  assert.equal(request.content.title, '미팅 대표 제목')
  assert.equal(request.deal_sections.length, 1)
  assert.deepEqual(request.deal_sections[0].content, {
    product: '제품 1',
    title: '딜 1 제목',
    values: { body: '딜 1 본문' },
    evidence: '근거 1',
  })
  assert.equal('ai_evidence' in request.deal_sections[0], false)
  assert.equal('ai_values' in request.deal_sections[0].content, false)
})

test('일정의 수정중 초안은 Compose로, 제출한 보고서는 단일 상세로 연결한다', () => {
  const draft = toMeetingReport({ ...response({ body: '초안' }), status_code: 'draft' })
  const submitted = toMeetingReport({
    ...response({ body: '제출본' }),
    status_code: 'submitted',
  })

  assert.equal(draft.status, '수정중')
  assert.equal(meetingLinkFor(draft.agendaId, [draft]).to, `/meetings/new?agenda=${draft.agendaId}`)
  assert.equal(meetingLinkFor(draft.agendaId, [draft]).label, '이어서 작성')
  assert.equal(meetingLinkFor(submitted.agendaId, [submitted]).to, `/meetings/${submitted.id}`)
  assert.equal(meetingLinkFor(submitted.agendaId, [submitted]).label, '보고서 열기')
})

test('전체 목록과 달력은 일반 draft를 유지하고 미팅 draft만 제외한다', () => {
  assert.deepEqual(historyQueryScopes('all'), [
    { report_kind: ['daily', 'weekly', 'monthly'] },
    {
      report_kind: ['meeting'],
      status_code: ['submitted', 'approved', 'rejected', 'changes_requested'],
    },
  ])
  assert.deepEqual(historyQueryScopes('all', ['draft']), [
    { report_kind: ['daily', 'weekly', 'monthly'], status_code: ['draft'] },
  ])
  assert.deepEqual(historyQueryScopes('all', ['draft', 'approved']), [
    {
      report_kind: ['daily', 'weekly', 'monthly'],
      status_code: ['draft', 'approved'],
    },
    { report_kind: ['meeting'], status_code: ['approved'] },
  ])
})

test('V2 이전 제출본은 submission id 없이 검토 요청해 서버가 스냅샷하게 한다', async () => {
  const originalAdapter = client.defaults.adapter
  let sent
  client.defaults.adapter = async (config) => {
    sent = JSON.parse(config.data)
    return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
  }
  try {
    await reviewReport('legacy-report', null, 'approve', null)
  } finally {
    client.defaults.adapter = originalAdapter
  }

  assert.equal(sent.expected_submission_id, null)
  assert.equal(sent.expected_status_code, 'submitted')
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
