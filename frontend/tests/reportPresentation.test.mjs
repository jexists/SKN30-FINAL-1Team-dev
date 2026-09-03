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
const { fetchAllReportPages, historyQueryScopes } = await vite.ssrLoadModule(
  '/src/pages/Daily/useReportHistory.ts',
)
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
  ownPeriodReportQuery,
  periodFinalizeRequestOf,
  periodGenerationRequestOf,
  periodGenerationSeedOf,
  toReport,
} = await vite.ssrLoadModule('/src/pages/Daily/useDailyReports.ts')
const { mergeGeneratedValues, mergeSourceActivities } = await vite.ssrLoadModule(
  '/src/pages/Daily/useDailyDraft.ts',
)
const {
  hasMeetingDraftContent,
  invalidateMeetingGeneration,
  isMeetingBodyBlank,
  mergeMeetingGeneratedValues,
} = await vite.ssrLoadModule('/src/pages/Meetings/useMeetingDraft.ts')
const { toHtml, toMarkdown } = await vite.ssrLoadModule('/src/pages/Meetings/reportDocument.ts')
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
  body: typeof values.body === 'string' ? values.body : null,
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

test('기간 보고서 상세는 저장 스냅샷과 구조화 값을 무시하고 canonical 본문만 표시한다', () => {
  const report = toReport(
    periodResponse({ body: '실제 canonical 본문', structuredValues: { summary: '기존 요약' } }),
  )
  const view = renderToStaticMarkup(
    createElement(ReportFields, {
      template: report.template,
      values: report.values,
      readOnly: true,
    }),
  )
  assert.deepEqual(
    report.template.fields.map((field) => field.id),
    ['body'],
  )
  assert.deepEqual(report.values, { body: '실제 canonical 본문' })
  assert.match(view, /실제 canonical 본문/)
  assert.doesNotMatch(view, /기존 요약/)

  const contentOnly = periodResponse()
  contentOnly.content = { values: { body: '구형 content 본문' } }
  assert.deepEqual(toReport(contentOnly).values, { body: '' })
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
    [{ decision: '구형 결정 사항' }, '미팅 기록 확정'],
    [{ note: '구형 메모' }, '미팅 기록 확정'],
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

test('미팅 목록은 공통·미지정·딜별 canonical 본문 전문을 순서대로 보존한다', () => {
  const raw = response({ custom: '구형 값', body: '딜 본문 첫 문단\n둘째 문단' }, [
    { id: 'custom', label: '구형 필드', type: 'textarea' },
  ])
  raw.common_body = '공통 본문'
  raw.unassigned_body = '미지정 본문'
  const row = fromMeetingReport(toMeetingReport(raw))

  assert.equal(row.body, '공통 본문\n\n미지정 본문\n\n딜 본문 첫 문단\n둘째 문단')
  assert.doesNotMatch(row.body, /구형 값/)
})

test('미팅 편집기는 canonical Markdown 본문 하나를 HTML과 왕복한다', () => {
  const markdown = '## 미팅 결과\n\n첫 문단입니다.\n\n- 후속 연락\n- 견적 전달'
  const html = toHtml(markdown)

  assert.match(html, /<h2>미팅 결과<\/h2>/)
  assert.match(html, /<li>후속 연락<\/li>/)
  assert.equal(toMarkdown(html), markdown)
  assert.equal(toMarkdown(toHtml('첫째 줄\n둘째 줄')), '첫째 줄\n둘째 줄')

  const unsafe = toHtml(
    '[외부 링크](javascript:alert(1)) ![외부 이미지](https://example.invalid/a.png)\n\n<script>alert(1)</script>',
  )
  assert.doesNotMatch(unsafe, /(?:href|src)=|<script/i)
  assert.match(unsafe, /&lt;script&gt;/)
})

test('미팅 생성 근거가 바뀌면 이전 run 연결만 버리고 사람이 검토 중인 본문은 유지한다', () => {
  const shared = { common_report: { body: '검토 중인 공통 본문', evidence_ids: [] } }

  assert.deepEqual(invalidateMeetingGeneration({ runId: 'old-run', shared }), {
    runId: undefined,
    shared,
  })
  assert.equal(invalidateMeetingGeneration(null), null)
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

test('미팅 응답·생성·확정은 저장된 구형 필드 대신 canonical body 하나만 사용한다', () => {
  const legacySection = {
    ...dealSection({ body: 'content의 canonical 본문', attendees: '구형 참석자' }),
    body: 'DB canonical 본문',
    structured_values: {
      attendees: '기존 참석자',
      reaction: '기존 고객 반응',
    },
  }
  const raw = response(
    {},
    [{ id: 'attendees', label: '구형 참석자', type: 'text' }],
    [legacySection],
  )
  raw.status_code = 'draft'
  raw.version = 4
  const report = toMeetingReport(raw)

  assert.deepEqual(report.dealSections[0].values, { body: 'DB canonical 본문' })
  assert.deepEqual(
    report.template.fields.map((field) => field.id),
    ['body'],
  )
  assert.deepEqual(
    toMeetingReport(
      response({}, [], [{ ...dealSection({ body: '구형 content 본문' }), body: null }]),
    ).dealSections[0].values,
    { body: '' },
  )

  const generated = mergeMeetingGeneratedValues('새 AI 미팅 본문')
  assert.deepEqual(generated, { body: '새 AI 미팅 본문' })
  assert.equal(meetingBodyOf(generated), '새 AI 미팅 본문')
  assert.equal(meetingBodyOf({}), '')

  const draft = {
    reportId: report.id,
    version: report.version,
    statusCode: 'draft',
    agendaId: report.agendaId,
    date: report.date,
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
  const finalized = meetingFinalizeRequestOf(draft, 'body-finalize')

  assert.equal(finalized.deal_sections[0].body, '새 AI 미팅 본문')
  assert.deepEqual(finalized.deal_sections[0].structured_values, {})
  assert.deepEqual(finalized.deal_sections[0].content.values, { body: '새 AI 미팅 본문' })
  assert.equal(finalized.report_id, report.id)
  assert.equal(finalized.expected_status_code, 'draft')
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

test('팀장 검토 화면은 저장된 Markdown을 서식으로 표시하되 raw HTML은 실행하지 않는다', () => {
  const raw = response(
    {},
    [{ id: 'body', label: '본문' }],
    [dealSection({ body: '**중요 합의**\n\n- 후속 연락\n\n<script>alert(1)</script>' })],
  )
  const view = renderToStaticMarkup(
    createElement(ReportReviewContents, { report: toMeetingReport(raw) }),
  )

  assert.match(view, /<strong>중요 합의<\/strong>/)
  assert.match(view, /<li>후속 연락<\/li>/)
  assert.doesNotMatch(view, /<script/i)
  assert.match(view, /&lt;script&gt;/)
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
  assert.equal(canonical.template_snapshot.id, 'builtin-meeting-freeform')
  assert.deepEqual(
    canonical.template_snapshot.fields.map((field) => field.id),
    ['body'],
  )
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

test('기간 생성과 최종 확정은 guidance·범위와 canonical body 하나만 제출한다', () => {
  const draft = {
    date: '2026-08-31',
    kind: '주간',
    approver: '합성 팀장',
    values: { body: '주간 보고서 전문' },
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
  assert.equal(generation.template_snapshot.id, 'builtin-weekly-freeform')
  assert.deepEqual(
    generation.template_snapshot.fields.map((field) => field.id),
    ['body'],
  )
  assert.deepEqual(generation.content.values, { body: '주간 보고서 전문' })
  assert.equal('transcript' in generation, false)
  assert.equal('source_activity_id' in generation, false)
  assert.equal('sales_deal_ids' in generation, false)

  assert.equal(finalized.idempotency_key, 'period-finalize-key')
  assert.equal(finalized.agent_run_id, 'period-run')
  assert.equal(finalized.body, '주간 보고서 전문')
  assert.deepEqual(finalized.structured_values, {})
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

test('재접속 입력은 원문·첨부·자료와 canonical body만 되살린다', () => {
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
      values: { body: '생성 전 본문', summary: '무시할 구형 요약' },
      activities: [activity],
      attachments: [attachment],
    },
    transcript: null,
    guidance: '복구할 직접 입력',
  })
  assert.equal(periodSeed.transcript, '복구할 직접 입력')
  assert.deepEqual(periodSeed.activities, [activity])
  assert.deepEqual(periodSeed.attachments, [attachment])
  assert.deepEqual(periodSeed.values, { body: '생성 전 본문' })
  assert.deepEqual(
    mergeGeneratedValues([
      { field_id: 'summary', value: '무시할 구형 AI 요약' },
      { field_id: 'body', value: '복구한 AI 본문' },
    ]),
    { body: '복구한 AI 본문' },
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
  assert.equal('template' in meetingSeed, false)

  assert.equal(isMeetingBodyBlank({ body: '' }), true)
  assert.equal(isMeetingBodyBlank({ body: '   ' }), true)
  assert.equal(isMeetingBodyBlank({ body: '수동 작성 본문' }), false)

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

test('달력 보고서는 30건을 넘어도 다음 쪽을 끝까지 이어 받는다', async () => {
  const originalAdapter = client.defaults.adapter
  const skips = []
  client.defaults.adapter = async (config) => {
    const skip = config.params.skip
    skips.push(skip)
    const first = skip === 0
    return {
      data: {
        items: Array.from({ length: first ? 30 : 1 }, (_, index) => ({
          id: `report-${skip + index}`,
        })),
        skip,
        limit: 30,
        total: 31,
        has_more: first,
        next_skip: first ? 30 : null,
      },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    }
  }
  try {
    const reports = await fetchAllReportPages({ report_kind: ['daily'] })
    assert.equal(reports.length, 31)
    assert.deepEqual(skips, [0, 30])
  } finally {
    client.defaults.adapter = originalAdapter
  }
})

test('달력 보고서 조회는 서버 쪽 번호가 전진하지 않으면 즉시 중단한다', async () => {
  const originalAdapter = client.defaults.adapter
  client.defaults.adapter = async (config) => ({
    data: {
      items: [],
      skip: config.params.skip,
      limit: 30,
      total: 99,
      has_more: true,
      next_skip: config.params.skip,
    },
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
  })
  try {
    await assert.rejects(fetchAllReportPages({ report_kind: ['daily'] }), /invalid_pagination/)
  } finally {
    client.defaults.adapter = originalAdapter
  }
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
