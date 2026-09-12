import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { after, test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

// 기존 Vite 변환으로 실제 TS/TSX를 읽는다. HTTP 서버나 업무 API는 호출하지 않는다.
const vite = await createServer({
  envDir: false,
  server: { middlewareMode: true, hmr: false, ws: false },
  define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('http://synthetic.invalid') },
})
after(() => vite.close())
const { activityLink, meetingLinkFor, sourcesFor } = await vite.ssrLoadModule(
  '/src/pages/Daily/sources.ts',
)
const { dealDetailPath } = await vite.ssrLoadModule('/src/constants/routes.ts')
const { fromMeetingReport } = await vite.ssrLoadModule('/src/pages/Daily/rows.ts')
const { fetchAllReportPages } = await vite.ssrLoadModule('/src/shared/reportQuery.ts')
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
  childReportQuery,
  ownPeriodReportQuery,
  periodFinalizeRequestOf,
  periodGenerationRequestOf,
  periodGenerationSeedOf,
  toReport,
} = await vite.ssrLoadModule('/src/pages/Daily/useDailyReports.ts')
const { mergeGeneratedValues } = await vite.ssrLoadModule('/src/pages/Daily/useDailyDraft.ts')
const { reportInputError } = await vite.ssrLoadModule('/src/shared/reports.ts')
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
const { default: ActivityList } = await vite.ssrLoadModule(
  '/src/pages/Daily/components/ActivityList/ActivityList.tsx',
)
const { default: MeetingInfoPanel } = await vite.ssrLoadModule(
  '/src/pages/Meetings/components/MeetingInfoPanel/MeetingInfoPanel.tsx',
)
const { default: AttachmentPanel } = await vite.ssrLoadModule(
  '/src/components/AttachmentPanel/AttachmentPanel.tsx',
)
const { default: MeetingInputPanel } = await vite.ssrLoadModule(
  '/src/pages/Meetings/components/MeetingInputPanel/MeetingInputPanel.tsx',
)
const { attachmentPayloadsOf, attachmentsFromPayload, meetingAttachmentPurposeOf } =
  await vite.ssrLoadModule('/src/utils/attachment.ts')
const { initScope, resetScope } = await vite.ssrLoadModule('/src/shared/scope.ts')
const { default: MeetingSharedPanel } = await vite.ssrLoadModule(
  '/src/pages/Meetings/components/MeetingSharedPanel.tsx',
)
const { ReportReviewContents } = await vite.ssrLoadModule(
  '/src/pages/Dashboard/components/ReportReviewDrawer/ReportReviewDrawer.tsx',
)
const { reviewReport } = await vite.ssrLoadModule('/src/shared/reviewDecision.ts')
const { client } = await vite.ssrLoadModule('/src/api/client.ts')
const { downloadReportAttachment } = await vite.ssrLoadModule('/src/api/reportAttachments.ts')
const { messageForCode, reportGenerationMessage } = await vite.ssrLoadModule(
  '/src/api/errorMessage.ts',
)

test('딜 상세 링크는 식별자를 인코딩해 영업 현황 드로어를 바로 연다', () => {
  assert.equal(dealDetailPath('deal/id?tab=1'), '/deals?deal=deal%2Fid%3Ftab%3D1')
})

test('첨부판은 허용 형식과 업로드 상태·조작 대상을 보조기기에 알린다', () => {
  const view = renderToStaticMarkup(
    createElement(AttachmentPanel, {
      attachments: [
        {
          id: 'pending-audio',
          kind: 'audio',
          name: 'meeting.mp3',
          byteSize: 12 * 1024,
          state: 'analyzing',
        },
        {
          id: 'ready-pdf',
          kind: 'pdf',
          name: 'proposal.pdf',
          byteSize: 24 * 1024,
          state: 'done',
          extract: '분석 결과',
        },
      ],
      onAttach() {},
      onRemove() {},
    }),
  )

  assert.match(view, /aria-busy="true"/)
  assert.match(view, /accept="\.mp3,\.m4a,\.wav,\.webm,\.png,\.jpg,\.jpeg,\.webp,\.pdf"/)
  assert.match(view, /aria-label="첨부 파일 선택"/)
  assert.match(view, /role="status"[^>]*>12KB · 업로드·분석 중…/)
  assert.match(view, /aria-label="meeting\.mp3 업로드 취소"/)
  assert.match(view, /aria-controls="[^"]+-ready-pdf-extract"/)
})

test('미팅 입력은 형식과 목적을 분리하고 직접 입력을 파일 밖에 둔다', () => {
  const attachments = [
    {
      id: 'source-photo',
      kind: 'image',
      purpose: 'meeting_source',
      name: '원문.jpg',
      byteSize: 1,
      state: 'done',
      extract: '실제 기록',
    },
    {
      id: 'reference-audio',
      kind: 'audio',
      purpose: 'reference',
      name: '참고.mp3',
      byteSize: 1,
      state: 'done',
      extract: '제품 설명',
    },
  ]
  const view = renderToStaticMarkup(
    createElement(MeetingInputPanel, {
      attachments,
      transcript: '직접 기록',
      onAttach() {},
      onRemoveAttachment() {},
      onExtractChange() {},
      onTranscriptChange() {},
      attachmentError: null,
      disabled: false,
    }),
  )
  const [source, reference] = view.split('보고서 참고자료')
  assert.match(source, /미팅 원문/)
  assert.match(source, /원문\.jpg/)
  assert.doesNotMatch(source, /참고\.mp3/)
  assert.match(source, /<\/ul>[\s\S]*<label[^>]*for="transcript"[^>]*>직접 입력/)
  assert.match(reference, /참고\.mp3/)
  assert.match(reference, /미팅 발언으로 사용하지 않습니다/)
  assert.doesNotMatch(reference, /<textarea/)
})

test('첨부 목적과 교정문은 왕복 보존하고 과거 목적 누락은 임의로 채우지 않는다', () => {
  const attachments = [
    {
      id: 'source',
      kind: 'image',
      purpose: 'meeting_source',
      name: '원문.jpg',
      byteSize: 1,
      state: 'done',
      extract: '교정한 원문',
      originalStored: true,
    },
    {
      id: 'reference',
      kind: 'audio',
      purpose: 'reference',
      name: '참고.mp3',
      byteSize: 2,
      state: 'done',
      extract: '배경 설명',
    },
    {
      id: 'legacy',
      kind: 'audio',
      name: '과거.mp3',
      byteSize: 3,
      state: 'done',
      extract: '과거 기록',
    },
  ]
  const restored = attachmentsFromPayload(attachmentPayloadsOf(attachments))
  assert.deepEqual(restored, attachments)
  assert.equal(meetingAttachmentPurposeOf(restored[0]), 'meeting_source')
  assert.equal(meetingAttachmentPurposeOf(restored[1]), 'reference')
  assert.equal(meetingAttachmentPurposeOf(restored[2]), 'meeting_source')
  assert.equal('purpose' in attachmentPayloadsOf(restored)[2], false)
  assert.equal('original_stored' in attachmentPayloadsOf(restored)[2], false)
})

test('보관된 원본은 교정문을 비워도 제출하며 완료 전 파일과 과거 빈 추출문은 제외한다', () => {
  const file = {
    id: 'stored-empty',
    kind: 'image',
    purpose: 'meeting_source',
    name: '원문.png',
    byteSize: 68,
    state: 'done',
    extract: '',
    originalStored: true,
  }
  const payloads = attachmentPayloadsOf([
    file,
    { ...file, id: 'legacy-empty', originalStored: undefined },
    { ...file, id: 'pending', state: 'analyzing' },
    { ...file, id: 'failed', state: 'failed' },
  ])
  assert.equal(payloads.length, 1)
  assert.equal(payloads[0].extract, '')
  assert.equal(payloads[0].original_stored, true)
  assert.deepEqual(attachmentsFromPayload(payloads), [file])
})

test('완료 첨부판은 보관된 파일의 원본 기능과 구버전 원본 없음 안내를 구분한다', () => {
  const files = attachmentsFromPayload([
    {
      id: 'stored',
      kind: 'image',
      name: '보관.png',
      byte_size: 68,
      extract: '기록',
      original_stored: true,
    },
    { id: 'legacy', kind: 'pdf', name: '과거.pdf', byte_size: 10, extract: '과거 추출문' },
  ])
  const view = renderToStaticMarkup(
    createElement(AttachmentPanel, {
      attachments: files,
      reportId: 'synthetic-report',
      readOnly: true,
    }),
  )
  assert.equal((view.match(/>원본 보기<\/button>/g) ?? []).length, 1)
  assert.equal((view.match(/>다운로드<\/button>/g) ?? []).length, 1)
  assert.match(view, /원본 파일이 저장되지 않아 확인할 수 없습니다/)
  assert.doesNotMatch(view, /type="file"|업로드 취소|aria-label=".* 삭제"/)
})

test('원본 조회는 인증 클라이언트의 blob을 받고 JSON 오류도 사용자 오류로 읽는다', async () => {
  const originalAdapter = client.defaults.adapter
  const binary = new Blob(['synthetic original'], { type: 'application/pdf' })
  const signal = new AbortController().signal
  try {
    client.defaults.adapter = async (config) => {
      assert.equal(config.url, '/reports/synthetic-report/attachments/synthetic-file/download')
      assert.equal(config.responseType, 'blob')
      assert.equal(config.timeout, 300_000)
      assert.equal(config.signal, signal)
      return { data: binary, status: 200, statusText: 'OK', headers: {}, config }
    }
    assert.equal(
      await downloadReportAttachment('synthetic-report', 'synthetic-file', signal),
      binary,
    )
    client.defaults.adapter = async (config) => {
      throw Object.assign(new Error('expired'), {
        isAxiosError: true,
        config,
        response: {
          status: 409,
          data: new Blob([JSON.stringify({ detail: 'report_attachment_expired' })], {
            type: 'application/json',
          }),
        },
      })
    }
    await assert.rejects(
      downloadReportAttachment('synthetic-report', 'synthetic-file'),
      (error) => {
        assert.equal(error.response.data.detail, 'report_attachment_expired')
        assert.match(messageForCode(error.response.data.detail, '실패'), /다시.*첨부|다시.*올려/)
        return true
      },
    )
  } finally {
    client.defaults.adapter = originalAdapter
  }
})

test('기간 새 생성은 첨부 추출문을 참고자료로 보내고 메모를 지침으로 보낸다', () => {
  for (const kind of ['일일', '주간', '월간']) {
    const request = periodGenerationRequestOf(
      {
        date: '2026-09-01',
        kind,
        approver: '',
        values: { body: '이전 본문' },
        activities: [],
        transcript: '이전 지침',
        attachments: [
          {
            id: 'legacy-audio',
            kind: 'audio',
            name: '설명.mp3',
            byteSize: 100,
            state: 'done',
            extract: '참고할 제품 설명',
          },
        ],
      },
      'period-new',
    )
    assert.equal(request.attachments[0].purpose, 'reference')
    assert.equal(request.guidance, '이전 지침')
    assert.equal('transcript' in request, false)
    assert.equal(request.content.values.body, '이전 본문')
  }
})

test('기간 메모는 guidance 2,000자 경계를 사용하고 최종 제출에는 transcript로 보존한다', () => {
  const base = {
    date: '2026-09-01',
    kind: '주간',
    approver: '',
    values: { body: '' },
    activities: [],
    attachments: [],
  }
  const memo = '😀'.repeat(2_000)
  const request = periodGenerationRequestOf({ ...base, transcript: memo }, 'memo-limit')
  assert.equal(request.guidance, memo)
  assert.equal(reportInputError(request), null)
  assert.equal(
    reportInputError(periodGenerationRequestOf({ ...base, transcript: `${memo}😀` }, 'too-long')),
    'guidance_too_large',
  )
  assert.equal(
    periodFinalizeRequestOf({ ...base, transcript: memo }, 'memo-finalize').transcript,
    memo,
  )
})

test('딜 드로어를 열고 닫아도 현재 목록 페이지를 초기화하지 않는다', async () => {
  const source = await readFile(new URL('../src/pages/Deals/Deals.tsx', import.meta.url), 'utf8')
  const drawerParam = source.slice(
    source.indexOf('const setOpenId = useCallback('),
    source.indexOf('const setPipeline = useCallback('),
  )

  assert.match(drawerParam, /if \(id\) next\.set\('deal', id\)/)
  assert.match(drawerParam, /else next\.delete\('deal'\)/)
  assert.match(drawerParam, /setParams\(next, \{ replace: true \}\)/)
  assert.doesNotMatch(drawerParam, /setParam\(|setPage\(/)
  assert.match(source, /skip: \(page - 1\) \* PAGE_SIZE/)
})

const dealId = '10000000-0000-4000-8000-000000000001'
const dealSection = (values = {}, id = dealId, label = id === dealId ? 'DEAL-1' : 'DEAL-2') => ({
  sales_deal_id: id,
  deal_snapshot: { id, label },
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
  content: { title: '합성 보고서', hospital: '합성 고객사' },
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
  updated_at: '2026-08-31T10:00:00Z',
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

test('완료 미팅과 기간 보고서는 원본 목록을 복구하고 빈 직접 입력을 canonical 원문과 구분한다', () => {
  const attachment = {
    id: 'stored-source',
    kind: 'image',
    purpose: 'meeting_source',
    name: '기록.png',
    byte_size: 68,
    extract: '파일에서 읽은 기록',
    original_stored: true,
  }
  const raw = {
    ...response(),
    transcript: '파일에서 읽은 기록',
    direct_transcript: '',
    attachments: [attachment],
  }
  const meeting = toMeetingReport(raw)
  assert.equal(meeting.transcript, '파일에서 읽은 기록')
  assert.equal(meeting.directTranscript, '')
  assert.deepEqual(attachmentPayloadsOf(meeting.attachments), [attachment])
  assert.equal(toMeetingReport({ ...raw, direct_transcript: null }).directTranscript, undefined)
  const seed = meetingGenerationSeedOf({
    sales_deal_ids: [],
    transcript: '',
    attachments: [attachment],
  })
  assert.equal(seed.transcript, '')
  assert.deepEqual(attachmentPayloadsOf(seed.attachments), [attachment])
  for (const report_kind of ['daily', 'weekly', 'monthly']) {
    const reference = { ...attachment, purpose: 'reference' }
    const period = toReport({
      ...periodResponse({ body: '보존할 본문' }),
      report_kind,
      attachments: [reference],
    })
    assert.deepEqual(attachmentPayloadsOf(period.attachments), [reference])
    assert.equal(period.values.body, '보존할 본문')
    const draft = {
      date: period.date,
      kind: period.kind,
      approver: '',
      values: period.values,
      activities: [],
      transcript: '',
      attachments: period.attachments,
    }
    assert.deepEqual(periodFinalizeRequestOf(draft, 'synthetic-finalize').attachments, [reference])
  }
  const draft = {
    agendaId: 'synthetic-meeting',
    date: '2026-09-07',
    time: '',
    hospital: '',
    dept: '',
    contact: '',
    place: '',
    title: '보존할 제목',
    transcript: '',
    attachments: meeting.attachments,
    dealSections: [],
  }
  assert.deepEqual(meetingFinalizeRequestOf(draft, 'synthetic-finalize').attachments, [attachment])
})

test('미팅 보고서 내부 오류 코드는 작성·상세 화면에서 사용자 문구로 바꾼다', async () => {
  const message = 'AI가 보고서 초안을 정상적으로 구성하지 못했습니다. 다시 시도해 주세요.'
  assert.equal(reportGenerationMessage('report_agent_output_invalid'), message)
  assert.match(reportGenerationMessage('future_internal_error_code'), /future_internal_error_code/)
  assert.match(messageForCode('report_attachment_ocr_too_large', '실패'), /페이지나 이미지/)

  const raw = response()
  raw.deal_sections[0].ai_evidence = { report_error: 'report_agent_output_invalid' }
  assert.equal(toMeetingReport(raw).dealSections[0].reportError, message)

  const [draftSource, composeSource] = await Promise.all([
    readFile(new URL('../src/pages/Meetings/useMeetingDraft.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/pages/Meetings/Compose.tsx', import.meta.url), 'utf8'),
  ])
  assert.match(draftSource, /reportGenerationMessage\(reportError\)/)
  assert.match(composeSource, /reportGenerationMessage\(message\)/)
})

test('기간 보고서 상세는 저장 스냅샷과 구조화 값을 무시하고 canonical 본문만 표시한다', () => {
  const body = '**오늘 한 일**\n\n실제 canonical 본문\n\n<script>alert(1)</script>'
  const report = toReport(periodResponse({ body, structuredValues: { summary: '기존 요약' } }))
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
  assert.deepEqual(report.values, { body })
  assert.match(view, /<p><strong>오늘 한 일<\/strong><\/p>\s*<p>실제 canonical 본문<\/p>/)
  assert.doesNotMatch(view, /<script/i)
  assert.match(view, /&lt;script&gt;/)
  assert.match(view, /실제 canonical 본문/)
  assert.doesNotMatch(view, /기존 요약/)

  const contentOnly = periodResponse()
  contentOnly.content = { values: { body: '구형 content 본문' } }
  assert.deepEqual(toReport(contentOnly).values, { body: '' })
})

test('기간 보고서는 본인 작성본이면 승인 전까지 수정할 수 있다', () => {
  const draft = toReport(periodResponse({ status: 'draft' }))
  const returned = toReport(
    periodResponse({ status: 'changes_requested', reviewNote: '수치를 보완해 주세요.' }),
  )

  assert.equal(canEditPeriodReport(draft, 'synthetic-author'), true)
  assert.equal(draft.updatedAt, '2026-08-31T10:00:00Z')
  assert.equal(canEditPeriodReport(returned, 'synthetic-author'), true)
  assert.equal(canEditPeriodReport(draft, 'another-member'), false)
  assert.equal(
    canEditPeriodReport(toReport(periodResponse({ status: 'submitted' })), 'synthetic-author'),
    true,
  )
  assert.equal(
    canEditPeriodReport(toReport(periodResponse({ status: 'approved' })), 'synthetic-author'),
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

test('일일 관련 목록은 미팅일의 제출 보고서와 제출본 id만 연결하고 본문을 복사하지 않는다', () => {
  const raw = response({ body: '비공개 딜 본문' })
  raw.common_body = '비공개 공통 본문'
  raw.unassigned_body = '비공개 미지정 본문'
  raw.status_code = 'submitted'
  raw.current_submission_id = 'submission-1'
  const report = toMeetingReport(raw)
  const result = sourcesFor(
    '일일',
    report.date,
    [
      report,
      { ...report, id: 'outside-day', date: '2026-09-01' },
      { ...report, id: 'draft', status: '수정중' },
      { ...report, id: 'returned', status: '반려' },
    ],
    [],
  )
  assert.deepEqual(
    result.activities.map((activity) => activity.refId),
    [report.id],
  )
  const activity = result.activities[0]
  assert.equal(activity.source, '업무보고서')
  assert.equal(activityLink(activity), `/meetings/${report.id}`)
  assert.equal(result.meta.get(activity.id).to, activityLink(activity))
  // 미팅 보고서는 팀장 검토를 받지 않아 관련 목록에도 '작성완료'로만 섭니다.
  assert.equal(result.meta.get(activity.id).status, '작성완료')
  assert.doesNotMatch(JSON.stringify([...result.meta, result.activities]), /비공개/)
  assert.equal(activity.sourceSubmissionId, 'submission-1')
  assert.equal('values' in result, false)
  assert.deepEqual(sourcesFor('일일', report.date, [], []).activities, [])

  const view = renderToStaticMarkup(
    createElement(ActivityList, {
      activities: result.activities,
      renderAside: (row) => createElement('a', { href: activityLink(row) }, '원본 보기'),
    }),
  )
  assert.match(view, /합성 보고서/)
  assert.match(view, /합성 고객사/)
  assert.match(view, /href="\/meetings\/[^"]+"/)
  assert.doesNotMatch(view, /<button|aria-pressed|비공개|submission-1|사용한 확정본/)
})

test('주·월 관련 목록은 하위 종류·기간으로 걸러도 같은 날 다른 작성자의 보고서를 보존한다', () => {
  const daily = toReport(periodResponse({ status: 'submitted', body: '하위 보고서 본문' }))
  const dailyRows = [
    daily,
    { ...daily, id: 'second-author', owner: '다른 작성자' },
    { ...daily, id: 'other-week', date: '2026-09-06' },
    { ...daily, id: 'returned', status: '반려' },
    { ...daily, id: 'wrong-kind', kind: '월간' },
  ]
  const weekly = sourcesFor('주간', '2026-08-31', [], dailyRows)
  assert.deepEqual(
    weekly.activities.map((row) => row.refId),
    [daily.id, 'second-author'],
  )
  assert.equal(weekly.activities[0].source, '일일보고서')
  assert.equal(activityLink(weekly.activities[0]), `/daily/${daily.id}`)
  const weeks = ['2026-08-23', '2026-08-30', '2026-09-06', '2026-09-27', '2026-10-04'].map(
    (date) => ({ ...daily, id: date, kind: '주간', date }),
  )
  const monthly = sourcesFor('월간', '2026-09-01', [], weeks)
  assert.deepEqual(
    monthly.activities.map((row) => row.refId),
    ['2026-08-30', '2026-09-06', '2026-09-27'],
  )
  assert.equal(monthly.activities[0].source, '주간보고서')
  assert.equal('values' in monthly, false)
  assert.doesNotMatch(JSON.stringify(monthly.activities), /하위 보고서 본문/)
})

test('기간 상세는 저장된 관련 보고서만 탐색하고 구버전 일정 대체 목록을 표시하지 않는다', () => {
  const raw = periodResponse()
  raw.content.activities = [
    { id: 'calendar', source: '캘린더', included: true, refId: 'calendar' },
    { id: 'meeting', source: '업무보고서', included: true, refId: 'meeting' },
    { id: 'wrong-kind', source: '일일보고서', included: true, refId: 'daily' },
    { id: 'excluded', source: '업무보고서', included: false, refId: 'excluded' },
  ]
  assert.deepEqual(
    toReport(raw).activities.map((row) => row.refId),
    ['meeting'],
  )
  delete raw.content.activities
  raw.activities = [
    { activity_id: 'bare-calendar', title: '일정만 있음', starts_at: raw.report_date },
  ]
  const report = toReport(raw)
  assert.deepEqual(report.activities, [])
  const empty = renderToStaticMarkup(createElement(ActivityList, { activities: report.activities }))
  assert.match(empty, /이 기간에 제출된 관련 보고서가 없습니다/)
  assert.doesNotMatch(empty, /일정만 있음|생성할 수 없|작성하기/)
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

test('미팅 보고서 생성만 실패하면 사람이 작성한 공통 본문을 지우지 않는다', async () => {
  const source = await readFile(
    new URL('../src/pages/Meetings/useMeetingDraft.ts', import.meta.url),
    'utf8',
  )
  const acceptGenerated = source.slice(
    source.indexOf('const acceptGenerated'),
    source.indexOf('const generationFailed'),
  )

  assert.match(acceptGenerated, /setMeetingResult\(\(current\) =>/)
  assert.match(acceptGenerated, /: current\?\.shared/)
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
  const sources = sourcesFor('일일', report.date, [report], [])
  assert.equal(sources.activities.length, 1)
  assert.equal('values' in sources, false)
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

test('미팅 공통·미지정 기록은 목록 검색에 포함한다', () => {
  const raw = response({})
  raw.common_body = '공통 검색 전용 문구'
  raw.unassigned_body = '미지정 설명 첫 줄\n둘째 줄'
  const report = toMeetingReport(raw)
  const row = fromMeetingReport(report)

  assert.match(row.haystack, /공통 검색 전용 문구/)
  assert.match(row.haystack, /미지정 설명 첫 줄/)
})

test('미팅 생성은 AgentRun 입력만 보내고 최종 확정에만 전체 보고서와 revision을 보낸다', () => {
  const attachment = {
    id: '30000000-0000-4000-8000-000000000001',
    kind: 'pdf',
    name: 'proposal.pdf',
    byteSize: 12 * 1024,
    state: 'done',
    extract: '생성에만 쓰는 일회용 추출문',
  }
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
    attachments: [attachment],
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
    attachments: [
      {
        id: attachment.id,
        kind: attachment.kind,
        name: attachment.name,
        byte_size: attachment.byteSize,
        extract: attachment.extract,
      },
    ],
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
  assert.equal('attachments' in generation.content, false)
  const audioOnly = meetingGenerationRequestOf(
    {
      ...draft,
      transcript: '',
      attachments: [{ ...attachment, kind: 'audio', name: 'meeting.mp3' }],
    },
    'audio-only-generation-key',
  )
  assert.equal('transcript' in audioOnly, false)
  assert.equal(audioOnly.attachments[0].kind, 'audio')
  assert.equal(finalized.idempotency_key, 'meeting-finalize-key')
  assert.equal(finalized.agent_run_id, 'meeting-run')
  assert.deepEqual(finalized.attachments, generation.attachments)
  assert.equal('attachments' in finalized.content, false)
  assert.equal(JSON.stringify(finalized).includes(attachment.extract), true)
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
  const submitted = meetingFinalizeRequestOf(
    { ...draft, reportId: 'submitted-report', version: 3, statusCode: 'submitted' },
    'submitted-revision-key',
    'submitted-regeneration-run',
  )
  assert.equal(submitted.report_id, 'submitted-report')
  assert.equal(submitted.expected_version, 3)
  assert.equal(submitted.expected_status_code, 'submitted')
  assert.equal(submitted.agent_run_id, 'submitted-regeneration-run')
  assert.throws(
    () =>
      meetingFinalizeRequestOf(
        { ...draft, reportId: 'existing-report', statusCode: 'changes_requested' },
        'missing-version-key',
      ),
    /report_revision_required/,
  )
})

test('딜 미지정 미팅은 공통 본문만으로 생성·확정·검토할 수 있다', () => {
  const draft = {
    agendaId: 'unassigned-meeting',
    date: '2026-08-31',
    time: '10:00',
    hospital: '합성 고객사',
    dept: '구매팀',
    contact: '합성 담당자',
    place: '회의실',
    title: '첫 미팅',
    transcript: '고객의 현재 과제와 의사결정 구조를 확인했다.',
    attachments: [],
    dealSections: [],
    commonBody: '첫 미팅에서 확인한 핵심 정보',
  }

  const generation = meetingGenerationRequestOf(draft, 'unassigned-generation')
  const finalized = meetingFinalizeRequestOf(draft, 'unassigned-finalize')
  assert.deepEqual(generation.sales_deal_ids, [])
  assert.deepEqual(finalized.deal_sections, [])
  assert.equal(finalized.common_body, '첫 미팅에서 확인한 핵심 정보')

  const raw = response({}, [], [])
  raw.common_body = '첫 미팅에서 확인한 핵심 정보'
  const report = toMeetingReport(raw)
  const review = renderToStaticMarkup(createElement(ReportReviewContents, { report }))
  assert.equal(report.dealSections.length, 0)
  assert.match(review, /첫 미팅에서 확인한 핵심 정보/)
  assert.doesNotMatch(review, /딜별 보고서 내용을 찾을 수 없습니다/)

  const editor = renderToStaticMarkup(
    createElement(MeetingSharedPanel, { shared: null, showCommon: true, onChange() {} }),
  )
  assert.match(editor, /<label[^>]*>공통 내용<\/label>/)
  assert.match(editor, /<textarea/)
})

test('기간 새 생성은 참고첨부·범위·본문·메모를 쓰고 메모는 최종 저장에 보존한다', () => {
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
    attachments: [
      {
        id: '30000000-0000-4000-8000-000000000002',
        kind: 'image',
        name: 'memo.png',
        byteSize: 24 * 1024,
        state: 'done',
        extract: '생성에만 쓰는 이미지 추출문',
      },
      {
        id: '30000000-0000-4000-8000-000000000003',
        kind: 'pdf',
        name: 'failed.pdf',
        byteSize: 1024,
        state: 'failed',
        extract: '실패한 첨부는 전송하지 않는다',
      },
      {
        id: 'pending-file',
        kind: 'audio',
        name: 'pending.mp3',
        byteSize: 2 * 1024,
        state: 'analyzing',
      },
    ],
    transcript: '직접 쓴 생성 지침',
  }
  const generation = periodGenerationRequestOf(draft, 'period-generation-key')
  const finalized = periodFinalizeRequestOf(draft, 'period-finalize-key', 'period-run')

  assert.equal(generation.idempotency_key, 'period-generation-key')
  assert.equal(generation.report_kind, 'weekly')
  assert.equal(generation.period_start, '2026-08-30')
  assert.equal(generation.period_end, '2026-09-05')
  assert.equal(generation.guidance, '직접 쓴 생성 지침')
  assert.deepEqual(generation.attachments, [
    {
      id: draft.attachments[0].id,
      kind: 'image',
      purpose: 'reference',
      name: 'memo.png',
      byte_size: 24 * 1024,
      extract: '생성에만 쓰는 이미지 추출문',
    },
  ])
  assert.equal('attachments' in generation.content, false)
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
  assert.equal(finalized.attachments[0].extract, draft.attachments[0].extract)
  assert.equal('purpose' in finalized.attachments[0], false)
  assert.equal('attachments' in finalized.content, false)
  assert.equal(finalized.note, '관련 보고서 1건')
  assert.equal(JSON.stringify(finalized).includes(draft.attachments[0].extract), true)
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
  const submitted = periodFinalizeRequestOf(
    { ...draft, reportId: 'submitted-period', version: 5, statusCode: 'submitted' },
    'submitted-period-key',
  )
  assert.equal(submitted.expected_status_code, 'submitted')
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
  const attachment = {
    id: '30000000-0000-4000-8000-000000000004',
    kind: 'audio',
    name: 'meeting.mp3',
    byte_size: 4321,
    extract: '복구할 첨부 추출문',
  }
  const restoredAttachment = {
    id: attachment.id,
    kind: attachment.kind,
    name: attachment.name,
    byteSize: attachment.byte_size,
    state: 'done',
    extract: attachment.extract,
  }
  const periodSeed = periodGenerationSeedOf({
    report_kind: 'daily',
    report_date: '2026-08-31',
    period_start: null,
    period_end: null,
    source_activity_id: null,
    sales_deal_ids: [],
    attachments: [attachment],
    template_snapshot: template,
    content: {
      approver: '복구 팀장',
      values: { body: '생성 전 본문', summary: '무시할 구형 요약' },
      activities: [activity],
    },
    transcript: null,
    guidance: '복구할 직접 입력',
  })
  assert.equal(periodSeed.transcript, '복구할 직접 입력')
  assert.deepEqual(periodSeed.activities, [activity])
  assert.deepEqual(periodSeed.attachments, [restoredAttachment])
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
    attachments: [attachment],
    template_snapshot: template,
    content: {},
    transcript: null,
    guidance: null,
  })
  assert.equal(meetingSeed.reportDate, '2026-08-31')
  assert.deepEqual(meetingSeed.salesDealIds, [dealId])
  assert.equal(meetingSeed.transcript, '')
  assert.deepEqual(meetingSeed.attachments, [restoredAttachment])
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

test('일정의 보고서는 승인 전까지 Compose로 연결한다', () => {
  const draft = toMeetingReport({ ...response({ body: '초안' }), status_code: 'draft' })
  const submitted = toMeetingReport({
    ...response({ body: '제출본' }),
    status_code: 'submitted',
  })

  assert.equal(draft.status, '수정중')
  assert.equal(meetingLinkFor(draft.agendaId, [draft]).to, `/meetings/new?agenda=${draft.agendaId}`)
  assert.equal(meetingLinkFor(draft.agendaId, [draft]).label, '이어서 작성')
  assert.equal(
    meetingLinkFor(submitted.agendaId, [submitted]).to,
    `/meetings/new?agenda=${submitted.agendaId}`,
  )
  assert.equal(meetingLinkFor(submitted.agendaId, [submitted]).label, '수정하기')
})

test('일정 줄은 낸 보고서를 고치는 길을 세우지 않고 드로어만 승인 전 수정을 연다', async () => {
  const dayAgenda = await readFile(
    new URL('../src/pages/Dashboard/components/DayAgenda/DayAgenda.tsx', import.meta.url),
    'utf8',
  )
  const agendaReport = await readFile(
    new URL('../src/shared/agendaReport.ts', import.meta.url),
    'utf8',
  )

  // 줄에서는 안 쓴 것과 쓰다 만 것만 작성 화면으로 보냅니다. 낸 보고서는 상세로만
  // 가고, 고치는 것은 그 화면 끝의 '수정하기' 가 맡습니다.
  assert.doesNotMatch(dayAgenda, /보고서 수정/)
  assert.doesNotMatch(dayAgenda, /isAuthorEditableReportStatus\(/)
  assert.match(dayAgenda, /'계속 작성'/)
  assert.match(dayAgenda, /보고서 확인/)

  // 드로어는 지금도 승인 전 수정을 열므로 공통 규칙을 그대로 씁니다.
  assert.match(agendaReport, /isAuthorEditableReportStatus\(/)
})

test('미팅 탭은 초안까지 보여 상태 칩의 작성중이 비지 않는다', () => {
  assert.deepEqual(historyQueryScopes('meeting'), [{ report_kind: ['meeting'] }])
  assert.deepEqual(historyQueryScopes('meeting', ['draft']), [
    { report_kind: ['meeting'], status_code: ['draft'] },
  ])
  assert.deepEqual(
    historyQueryScopes('meeting', ['submitted', 'approved', 'rejected', 'changes_requested']),
    [
      {
        report_kind: ['meeting'],
        status_code: ['submitted', 'approved', 'rejected', 'changes_requested'],
      },
    ],
  )
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

test('관련 보고서는 종류·기간·작성자 범위를 유지하며 30건 다음 쪽까지 모두 표시한다', async () => {
  const originalAdapter = client.defaults.adapter
  try {
    for (const kind of ['일일', '주간', '월간']) {
      const params =
        kind === '일일'
          ? {
              report_kind: 'meeting',
              start_date: '2026-09-01',
              end_date: '2026-09-01',
              status_code: ['submitted', 'approved'],
            }
          : childReportQuery(kind, '2026-09-01')
      params.author_member_id = ['synthetic-team-member']
      const calls = []
      client.defaults.adapter = async (config) => {
        calls.push(config.params)
        const skip = config.params.skip
        const items = Array.from({ length: skip === 0 ? 30 : 1 }, (_, index) => ({
          ...(kind === '일일' ? response() : periodResponse({ status: 'submitted' })),
          id: `report-${skip + index}`,
          report_kind: params.report_kind,
          report_date: kind === '월간' ? '2026-08-30' : '2026-09-01',
        }))
        return {
          data: {
            items,
            skip,
            limit: 30,
            total: 31,
            has_more: skip === 0,
            next_skip: skip === 0 ? 30 : null,
          },
          status: 200,
          statusText: 'OK',
          headers: {},
          config,
        }
      }
      const rows = await fetchAllReportPages(params)
      const related = sourcesFor(
        kind,
        '2026-09-01',
        kind === '일일' ? rows.map(toMeetingReport) : [],
        kind === '일일' ? [] : rows.map(toReport),
      )
      assert.equal(related.activities.length, 31)
      assert.equal(related.activities.at(-1).refId, 'report-30')
      assert.deepEqual(
        calls.map(({ skip }) => skip),
        [0, 30],
      )
      for (const call of calls) assert.deepEqual(call, { ...params, skip: call.skip, limit: 30 })
      assert.equal(
        params.report_kind,
        kind === '일일' ? 'meeting' : kind === '주간' ? 'daily' : 'weekly',
      )
      assert.equal(params.start_date, kind === '일일' ? '2026-09-01' : '2026-08-30')
      assert.equal(
        params.end_date,
        kind === '일일' ? '2026-09-01' : kind === '주간' ? '2026-09-05' : '2026-09-30',
      )
    }
  } finally {
    client.defaults.adapter = originalAdapter
  }
})

test('보고서 페이지가 전진하지 않거나 다음 위치가 누락·범위를 벗어나면 실패를 표시한다', async () => {
  const originalAdapter = client.defaults.adapter
  try {
    for (const next of [0, null, 100, 1.5]) {
      let calls = 0
      client.defaults.adapter = async (config) => {
        calls += 1
        return {
          data: {
            items: [{ id: 'report' }],
            skip: 0,
            limit: 30,
            total: 99,
            has_more: true,
            next_skip: next,
          },
          status: 200,
          statusText: 'OK',
          headers: {},
          config,
        }
      }
      await assert.rejects(fetchAllReportPages({ report_kind: ['daily'] }), /invalid_pagination/)
      assert.equal(calls, 1)
    }
    client.defaults.adapter = async (config) => {
      if (config.params.skip > 0) throw new Error('second_page_failed')
      return {
        data: {
          items: [{ id: 'first-page-only' }],
          skip: 0,
          limit: 30,
          total: 2,
          has_more: true,
          next_skip: 1,
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }
    await assert.rejects(fetchAllReportPages({ report_kind: 'daily' }), /second_page_failed/)
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
  assert.match(view, /<h2[^>]*>미팅 공통 기록<\/h2>/)
  assert.doesNotMatch(view, /<h3[^>]*>공통 내용<\/h3>/)
  assert.match(view, /<h3[^>]*>딜 미지정 기록<\/h3>/)
  assert.doesNotMatch(view, /<label|<textarea/)
  assert.match(view, /공통 내용 본문/)
  assert.match(view, /미지정 내용 본문/)
  const edit = renderToStaticMarkup(createElement(MeetingSharedPanel, { shared, onChange() {} }))
  const labels = [...edit.matchAll(/<label for="([^"]+)">/g)]
  assert.equal(labels.length, 2)
  for (const [, id] of labels) assert(edit.includes(`<textarea id="${id}"`))
})

test('미팅 공통 기록은 재생성 중 이전 내용 대신 진행 상태를 표시한다', () => {
  const view = renderToStaticMarkup(
    createElement(MeetingSharedPanel, {
      shared: { common_report: { body: '기존 공통 기록', evidence_ids: [] } },
      generating: true,
    }),
  )

  assert.match(view, /aria-busy="true"/)
  assert.match(view, /role="status"/)
  assert.match(view, /aria-live="polite"/)
  assert.match(view, /미팅 처리를 준비하는 중입니다/)
  assert.doesNotMatch(view, /기존 공통 기록/)
})

test('딜별 보고서는 재생성 중 이전 제목 대신 로딩 자리를 표시한다', async () => {
  const source = await readFile(
    new URL('../src/pages/Meetings/components/ReportSheet/ReportSheet.tsx', import.meta.url),
    'utf8',
  )
  const titleBlock = source.slice(
    source.indexOf('<div className={styles.titleBlock}>'),
    source.indexOf('<p className={styles.when}>'),
  )

  assert.match(titleBlock, /phase === 'generating'/)
  assert.match(titleBlock, /<Skeleton width="68%" height=\{39\}/)
  assert.match(titleBlock, /:\s*\([\s\S]*<input/)
})

test('일일·주간·월간 생성과 확정은 해당 하위 종류의 참조·제출본·포함 여부를 그대로 전달한다', async () => {
  const originalAdapter = client.defaults.adapter
  const { createReportGeneration } = await vite.ssrLoadModule('/src/api/reportAgent.ts')
  const sent = []
  client.defaults.adapter = async (config) => {
    assert.equal(config.method, 'post')
    sent.push(JSON.parse(config.data))
    return {
      data: { id: 'synthetic-run', status_code: 'queued' },
      status: 202,
      statusText: 'OK',
      headers: {},
      config,
    }
  }
  try {
    for (const kind of ['일일', '주간', '월간']) {
      const draft = {
        date: '2026-09-01',
        kind,
        approver: '',
        values: { body: '' },
        activities: [],
        attachments: [],
        transcript: '',
      }
      const request = periodGenerationRequestOf(draft, `scope-${kind}`)
      assert.equal(
        request.report_kind,
        kind === '일일' ? 'daily' : kind === '주간' ? 'weekly' : 'monthly',
      )
      assert.equal(request.report_date, kind === '주간' ? '2026-08-30' : '2026-09-01')
      assert.equal(
        request.period_end,
        kind === '일일' ? undefined : kind === '주간' ? '2026-09-05' : '2026-09-30',
      )
      const related = sourcesFor(
        kind,
        draft.date,
        [
          toMeetingReport({
            ...response({ body: '관련 카드의 미팅 본문' }),
            current_submission_id: 'meeting-submission',
            report_date: draft.date,
          }),
        ],
        [
          toReport({
            ...periodResponse({ body: '관련 카드의 기간 본문', status: 'submitted' }),
            current_submission_id: 'period-submission',
            report_kind: kind === '월간' ? 'weekly' : 'daily',
            report_date: draft.date,
          }),
        ],
      )
      const withRelated = { ...draft, activities: related.activities }
      const generation = periodGenerationRequestOf(withRelated, `hierarchy-${kind}`)
      await createReportGeneration(generation)
      assert.deepEqual(sent.at(-1).content.activities, related.activities)
      assert.equal(
        related.activities[0].source,
        kind === '일일' ? '업무보고서' : kind === '주간' ? '일일보고서' : '주간보고서',
      )
      assert.equal(
        related.activities[0].sourceSubmissionId,
        kind === '일일' ? 'meeting-submission' : 'period-submission',
      )
      const final = periodFinalizeRequestOf(
        { ...withRelated, values: { body: '사람이 확인한 최종 본문' } },
        'final',
      )
      assert.deepEqual(generation.content.activities, related.activities)
      assert.deepEqual(final.content.activities, related.activities)
      assert.doesNotMatch(JSON.stringify(generation), /관련 카드의|guidance/)
      assert.equal(final.body, '사람이 확인한 최종 본문')
    }
  } finally {
    client.defaults.adapter = originalAdapter
  }
})

test('다음 날 작성 완료·일정 이동 후 수정에도 기존 미팅일을 표시하고 요청에 보존한다', async () => {
  const raw = {
    ...response(),
    report_date: '2026-08-31',
    version: 3,
    updated_at: '2026-09-01T00:10:00Z',
  }
  const saved = toMeetingReport(raw)
  const item = {
    id: saved.agendaId,
    date: '2026-09-02',
    time: '11:00',
    hospital: '합성 고객사',
    contact: '담당자',
    dept: '',
    place: '',
  }
  const compose = await readFile(
    new URL('../src/pages/Meetings/Compose.tsx', import.meta.url),
    'utf8',
  )
  assert.match(
    compose,
    /const meetingDate = savedReport\?\.date \?\? draft\.reportDate \?\? item\.date/,
  )
  assert.match(compose, /date: meetingDate,\s+time: meetingTime/)
  assert.match(compose, /item=\{\{ \.\.\.item, date: meetingDate, time: meetingTime \}\}/)
  assert.doesNotMatch(compose, /작성 완료 후에도 이 날짜로 저장됩니다/)
  const meetingDate = saved.date ?? item.date
  const draft = {
    reportId: saved.id,
    version: saved.version,
    statusCode: 'submitted',
    agendaId: saved.agendaId,
    date: meetingDate,
    time: saved.time,
    hospital: saved.hospital,
    dept: '',
    contact: '',
    place: '',
    title: saved.title,
    transcript: '',
    attachments: [],
    dealSections: [],
    commonBody: '다음 날 확인한 미팅 본문',
  }
  const generation = meetingGenerationRequestOf(draft, 'late-generation')
  const final = meetingFinalizeRequestOf(draft, 'late-final')
  assert.equal(generation.report_date, '2026-08-31')
  assert.equal(final.report_date, '2026-08-31')
  assert.equal(final.report_id, saved.id)
  assert.equal('submitted_at' in final, false)
  assert.equal(
    meetingGenerationRequestOf({ ...draft, reportId: undefined, date: item.date }, 'new')
      .report_date,
    '2026-09-02',
  )
  const view = renderToStaticMarkup(
    createElement(MeetingInfoPanel, {
      item: { ...item, date: meetingDate, time: saved.time },
      deals: [],
      dealsLoading: false,
      dealsError: null,
      onReloadDeals() {},
      selectedDealIds: [],
      onToggleDeal() {},
      disabled: false,
    }),
  )
  assert.match(view, /미팅일 2026\.08\.31/)
  assert.doesNotMatch(view, /2026\.09\.02/)
})

test('기간 상세와 작성은 같은 현재 관련 조회를 사용하며 저장 시 없던 보고서도 연결한다', async () => {
  const [detail, draft, queries] = await Promise.all([
    readFile(new URL('../src/pages/Daily/Detail.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/pages/Daily/useDailyDraft.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/pages/Daily/useDailyReports.ts', import.meta.url), 'utf8'),
  ])
  assert.match(
    detail,
    /useRelatedReports\(report\?\.kind \?\? '일일', report\?\.date \?\? '', !!report\)/,
  )
  assert.match(detail, /activities=\{related\.activities\}/)
  assert.match(draft, /useRelatedReports\(kind, dateISO\)/)
  assert.match(queries, /'관련 보고서를 불러오지 못했습니다\.',\s+true,/)
  const parent = toReport({
    ...periodResponse(),
    report_kind: 'weekly',
    report_date: '2026-08-30',
    content: { activities: [] },
  })
  const laterChild = toReport({
    ...periodResponse({ status: 'submitted' }),
    id: 'later-daily',
    report_date: '2026-09-01',
  })
  const current = sourcesFor(parent.kind, parent.date, [], [laterChild])
  assert.deepEqual(parent.activities, [])
  assert.deepEqual(
    current.activities.map((row) => row.refId),
    ['later-daily'],
  )
  const view = renderToStaticMarkup(
    createElement(ActivityList, {
      activities: current.activities,
      renderAside: (row) => createElement('a', { href: activityLink(row) }, '원본 보기'),
    }),
  )
  assert.match(view, /href="\/daily\/later-daily"/)
  assert.doesNotMatch(view, /사용한 확정본|포함된 활동/)
})
