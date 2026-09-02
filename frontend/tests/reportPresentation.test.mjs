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
const {
  meetingBodyOf,
  meetingFinalizeRequestOf,
  meetingGenerationRequestOf,
  meetingGenerationSeedOf,
  meetingRequestOf,
  toMeetingReport,
} = await vite.ssrLoadModule('/src/pages/Meetings/useMeetingReports.ts')
const {
  canEditPeriodReport,
  detailTemplateOf,
  ownPeriodReportQuery,
  periodFinalizeRequestOf,
  periodGenerationRequestOf,
  periodGenerationSeedOf,
  toReport,
} = await vite.ssrLoadModule('/src/pages/Daily/useDailyReports.ts')
const { mergeGeneratedValues, mergeSourceActivities } = await vite.ssrLoadModule(
  '/src/pages/Daily/useDailyDraft.ts',
)
const { hasMeetingDraftContent, mergeMeetingGeneratedValues } = await vite.ssrLoadModule(
  '/src/pages/Meetings/useMeetingDraft.ts',
)
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

test('늦게 도착한 보고서 자료는 초기 초안에 반영하고 기존 선택은 보존한다', () => {
  const loaded = [
    {
      id: 'cal-first',
      source: '캘린더',
      title: '첫 번째 일정',
      desc: '',
      included: true,
      refId: 'first',
    },
    {
      id: 'cal-picked',
      source: '캘린더',
      title: '미리 고른 일정',
      desc: '',
      included: false,
      refId: 'picked',
    },
  ]

  const initialized = mergeSourceActivities(loaded, [], 'picked')
  assert.deepEqual(
    initialized.map(({ id, included }) => [id, included]),
    [
      ['cal-first', true],
      ['cal-picked', true],
    ],
  )

  const refreshed = mergeSourceActivities(
    [{ ...loaded[0], title: '갱신된 일정' }, loaded[1]],
    [{ ...initialized[0], included: false }, initialized[1]],
  )
  assert.equal(refreshed[0].title, '갱신된 일정')
  assert.equal(refreshed[0].included, false)
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

test('legacy 구조화 미팅은 custom 값을 보존하고 생성 본문을 별도 body로 제출한다', () => {
  const fields = [
    {
      id: 'attendees',
      label: '참석자',
      type: 'text',
      required: true,
      aiFilled: true,
    },
    {
      id: 'reaction',
      label: '고객 반응',
      type: 'textarea',
      required: true,
      aiFilled: true,
    },
    {
      id: 'manager_note',
      label: '관리자 메모',
      type: 'textarea',
      required: false,
      aiFilled: false,
    },
  ]
  const legacySection = {
    ...dealSection({}),
    body: null,
    structured_values: {
      attendees: '기존 참석자',
      reaction: '기존 고객 반응',
      manager_note: '사람이 쓴 메모',
    },
  }
  const raw = response({}, fields, [legacySection])
  raw.status_code = 'draft'
  raw.version = 4
  const report = toMeetingReport(raw)
  const restored = report.dealSections[0].values

  assert.deepEqual(restored, legacySection.structured_values)
  assert.deepEqual(
    report.template.fields.map((field) => field.id),
    ['attendees', 'reaction', 'manager_note', 'body'],
  )

  const generated = mergeMeetingGeneratedValues(restored, '새 AI 미팅 본문')
  assert.deepEqual(generated, {
    attendees: '기존 참석자',
    reaction: '기존 고객 반응',
    manager_note: '사람이 쓴 메모',
    body: '새 AI 미팅 본문',
  })
  assert.equal(meetingBodyOf(generated), '새 AI 미팅 본문')

  const draft = {
    reportId: report.id,
    version: report.version,
    statusCode: 'draft',
    agendaId: report.agendaId,
    date: report.date,
    template: report.template,
    time: report.time,
    hospital: report.hospital,
    dept: report.dept,
    contact: report.contact,
    place: report.place,
    title: report.title,
    transcript: report.transcript,
    attachments: report.attachments,
    dealSections: [
      {
        salesDealId: report.dealSections[0].salesDealId,
        salesDeal: report.dealSections[0].salesDeal,
        product: report.dealSections[0].product,
        title: report.dealSections[0].title,
        values: generated,
      },
    ],
  }
  const finalized = meetingFinalizeRequestOf(draft, 'legacy-structured-finalize')

  assert.equal(finalized.deal_sections[0].body, '새 AI 미팅 본문')
  assert.deepEqual(finalized.deal_sections[0].structured_values, legacySection.structured_values)
  assert.deepEqual(finalized.deal_sections[0].content.values, generated)
  assert.equal(finalized.report_id, report.id)
  assert.equal(finalized.expected_status_code, 'draft')

  const resumed = meetingFinalizeRequestOf(
    {
      ...draft,
      dealSections: [{ ...draft.dealSections[0], values: restored }],
    },
    'legacy-structured-resume',
  )
  assert.equal(resumed.deal_sections[0].body, null)
  assert.deepEqual(resumed.deal_sections[0].structured_values, legacySection.structured_values)
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
  raw.common_body = '검토할 공통 기록'
  raw.unassigned_body = '검토할 미지정 기록'

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
  raw.common_body = '공통 검색 전용 문구'
  raw.unassigned_body = '미지정 설명 첫 줄\n둘째 줄'
  const report = toMeetingReport(raw)
  const row = fromMeetingReport(report)

  assert.match(row.haystack, /공통 검색 전용 문구/)
  assert.match(row.haystack, /미지정 설명 첫 줄/)

  report.meetingShared.common_report = null
  const sources = sourcesFor('일일', report.date, [report], [], [])
  assert.equal(sources.activities[0].desc, '미지정 설명 첫 줄')
})

test('미팅 생성은 AgentRun 입력만 보내고 최종 확정에만 전체 보고서와 revision을 보낸다', () => {
  const draft = {
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
      },
    ],
    commonBody: '공통 내용',
    unassignedBody: '미지정 내용',
  }
  const canonical = meetingRequestOf(draft)
  const generation = meetingGenerationRequestOf(draft, 'meeting-generation-key')
  const finalized = meetingFinalizeRequestOf(draft, 'meeting-finalize-key', 'meeting-run')

  assert.deepEqual(generation, {
    idempotency_key: 'meeting-generation-key',
    report_kind: 'meeting',
    report_date: '2026-08-31',
    source_activity_id: 'synthetic-meeting',
    sales_deal_ids: [dealId],
    template_snapshot: canonical.template_snapshot,
    content: canonical.content,
    transcript: '합성 원문',
  })
  assert.equal('deal_sections' in generation, false)
  assert.equal(finalized.idempotency_key, 'meeting-finalize-key')
  assert.equal(finalized.agent_run_id, 'meeting-run')
  assert.equal(finalized.sales_deal_id, null)
  assert.equal(finalized.content.title, '미팅 대표 제목')
  assert.equal(finalized.common_body, '공통 내용')
  assert.equal(finalized.unassigned_body, '미지정 내용')
  assert.deepEqual(finalized.deal_sections[0].content, {
    product: '제품 1',
    title: '딜 1 제목',
    values: { body: '딜 1 본문' },
    evidence: '근거 1',
  })
  assert.equal('ai_evidence' in finalized.deal_sections[0], false)

  const revision = meetingFinalizeRequestOf(
    { ...draft, reportId: 'existing-report', version: 7, statusCode: 'changes_requested' },
    'meeting-revision-key',
    'meeting-run-2',
  )
  assert.equal(revision.report_id, 'existing-report')
  assert.equal(revision.expected_version, 7)
  assert.equal(revision.expected_status_code, 'changes_requested')
  const legacyDraft = meetingFinalizeRequestOf(
    { ...draft, reportId: 'legacy-draft', version: 2, statusCode: 'draft' },
    'legacy-draft-key',
  )
  assert.equal(legacyDraft.report_id, 'legacy-draft')
  assert.equal(legacyDraft.expected_version, 2)
  assert.equal(legacyDraft.expected_status_code, 'draft')
  assert.throws(
    () =>
      meetingFinalizeRequestOf(
        { ...draft, reportId: 'existing-report', statusCode: 'changes_requested' },
        'missing-version-key',
      ),
    /report_revision_required/,
  )
})

test('기간 생성은 guidance와 범위만 AgentRun에 보내고 최종 확정에서 전체 값을 제출한다', () => {
  const draft = {
    date: '2026-08-31',
    kind: '주간',
    approver: '합성 팀장',
    template: {
      id: 'weekly-template',
      name: '주간 양식',
      owner: '합성',
      updated: '',
      fields: [
        { id: 'summary', label: '요약', type: 'textarea', aiFilled: true },
        { id: 'memo', label: '메모', type: 'textarea', aiFilled: false },
      ],
    },
    values: { summary: '기존 요약', memo: '사람 메모' },
    activities: [
      {
        id: 'activity-1',
        source: '캘린더',
        title: '합성 일정',
        desc: '설명',
        included: true,
        refId: '20000000-0000-4000-8000-000000000001',
      },
    ],
    attachments: [{ id: 'file-1', name: 'memo.txt', state: 'ready' }],
    transcript: '직접 쓴 생성 지침',
  }
  const generation = periodGenerationRequestOf(draft, 'period-generation-key')
  const finalized = periodFinalizeRequestOf(draft, 'period-finalize-key', 'period-run')

  assert.equal(generation.idempotency_key, 'period-generation-key')
  assert.equal(generation.report_kind, 'weekly')
  assert.equal(generation.period_start, '2026-08-30')
  assert.equal(generation.period_end, '2026-09-05')
  assert.equal(generation.guidance, '직접 쓴 생성 지침')
  assert.deepEqual(generation.content.values, draft.values)
  assert.equal('transcript' in generation, false)
  assert.equal('source_activity_id' in generation, false)
  assert.equal('sales_deal_ids' in generation, false)

  assert.equal(finalized.idempotency_key, 'period-finalize-key')
  assert.equal(finalized.agent_run_id, 'period-run')
  assert.equal(finalized.body, null)
  assert.deepEqual(finalized.structured_values, draft.values)
  assert.equal(finalized.transcript, '직접 쓴 생성 지침')

  const revision = periodFinalizeRequestOf(
    { ...draft, reportId: 'existing-period', version: 3, statusCode: 'changes_requested' },
    'period-revision-key',
  )
  assert.deepEqual(
    {
      report_id: revision.report_id,
      expected_version: revision.expected_version,
      expected_status_code: revision.expected_status_code,
    },
    {
      report_id: 'existing-period',
      expected_version: 3,
      expected_status_code: 'changes_requested',
    },
  )
  const legacyDraft = periodFinalizeRequestOf(
    { ...draft, reportId: 'legacy-period-draft', version: 4, statusCode: 'draft' },
    'legacy-period-key',
  )
  assert.equal(legacyDraft.report_id, 'legacy-period-draft')
  assert.equal(legacyDraft.expected_version, 4)
  assert.equal(legacyDraft.expected_status_code, 'draft')
})

test('재접속 입력은 원문·첨부·자료를 되살리고 AI 결과는 직접 입력 필드를 보존한다', () => {
  const template = {
    id: 'recovery-template',
    name: '복구 양식',
    owner: '합성',
    updated: '',
    fields: [
      { id: 'summary', label: '요약', type: 'textarea', aiFilled: true },
      { id: 'memo', label: '메모', type: 'textarea', aiFilled: false },
    ],
  }
  const activity = {
    id: 'activity-1',
    source: '캘린더',
    title: '복구 일정',
    desc: '설명',
    included: true,
  }
  const attachment = { id: 'attachment-1', name: 'meeting.txt', state: 'ready' }
  const periodSeed = periodGenerationSeedOf({
    report_kind: 'daily',
    report_date: '2026-08-31',
    period_start: null,
    period_end: null,
    source_activity_id: null,
    sales_deal_ids: [],
    template_snapshot: template,
    content: {
      approver: '복구 팀장',
      values: { summary: '생성 전 요약', memo: '사람이 쓴 메모' },
      activities: [activity],
      attachments: [attachment],
    },
    transcript: null,
    guidance: '복구할 직접 입력',
  })
  assert.equal(periodSeed.transcript, '복구할 직접 입력')
  assert.deepEqual(periodSeed.activities, [activity])
  assert.deepEqual(periodSeed.attachments, [attachment])
  assert.deepEqual(
    mergeGeneratedValues(template, periodSeed.values, [
      { field_id: 'summary', value: '복구한 AI 요약' },
      { field_id: 'memo', value: '덮어쓰면 안 되는 값' },
    ]),
    { summary: '복구한 AI 요약', memo: '사람이 쓴 메모' },
  )

  const meetingSeed = meetingGenerationSeedOf({
    report_kind: 'meeting',
    report_date: '2026-08-31',
    period_start: null,
    period_end: null,
    source_activity_id: 'synthetic-meeting',
    sales_deal_ids: [dealId],
    template_snapshot: template,
    content: { attachments: [attachment] },
    transcript: '복구할 미팅 원문',
    guidance: null,
  })
  assert.deepEqual(meetingSeed.salesDealIds, [dealId])
  assert.equal(meetingSeed.transcript, '복구할 미팅 원문')
  assert.deepEqual(meetingSeed.attachments, [attachment])
  assert.deepEqual(
    meetingSeed.template.fields.map((field) => field.id),
    ['summary', 'memo', 'body'],
  )

  assert.equal(
    hasMeetingDraftContent(
      [dealId],
      { [dealId]: { values: { body: '' }, touched: true } },
      undefined,
    ),
    true,
    '본문이 비어도 사람이 제목을 고쳤으면 재생성 확인이 필요하다',
  )
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

test('공통·미지정 기록은 읽기 전용 제목과 편집용 연결 label을 구분한다', () => {
  const shared = {
    common_report: { body: '공통 내용 본문', evidence_ids: [] },
    unassigned_report: { body: '미지정 내용 본문', evidence_ids: [] },
  }
  const view = renderToStaticMarkup(createElement(MeetingSharedPanel, { shared }))
  assert.match(view, /<h3[^>]*>공통 내용<\/h3>/)
  assert.match(view, /<h3[^>]*>딜 미지정 · 확인 필요<\/h3>/)
  assert.doesNotMatch(view, /<label|<textarea/)
  assert.match(view, /공통 내용 본문/)
  assert.match(view, /미지정 내용 본문/)
  const edit = renderToStaticMarkup(createElement(MeetingSharedPanel, { shared, onChange() {} }))
  const labels = [...edit.matchAll(/<label for="([^"]+)">/g)]
  assert.equal(labels.length, 2)
  for (const [, id] of labels) assert(edit.includes(`<textarea id="${id}"`))
})
