import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { after, test } from 'node:test'
import { createServer } from 'vite'
import { AxiosError } from 'axios'

const vite = await createServer({
  envDir: false,
  server: { middlewareMode: true, hmr: false, ws: false },
  define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('http://synthetic.invalid') },
})
after(() => vite.close())

const {
  createReportGeneration,
  finalizeReport,
  finishIdempotencyAttempt,
  idempotencyAttemptFor,
  latestReportGeneration,
  latestMeetingProcessing,
  retryMeetingReport,
  sameReportGenerationInput,
  waitForMeetingAnalysis,
  waitForMeetingProcessing,
  waitForReportGeneration,
} = await vite.ssrLoadModule('/src/api/reportAgent.ts')
const { client } = await vite.ssrLoadModule('/src/api/client.ts')
const { uploadReportAttachment } = await vite.ssrLoadModule('/src/api/reportAttachments.ts')
const { kindOf } = await vite.ssrLoadModule('/src/shared/useAttachments.ts')
const { reportInputError, reportTextLength, REPORT_ATTACHMENT_LIMIT } =
  await vite.ssrLoadModule('/src/shared/reports.ts')
const { errorMessage, messageForCode } = await vite.ssrLoadModule('/src/api/errorMessage.ts')
const { AgentRunTerminalError } = await vite.ssrLoadModule('/src/api/meetingStream.ts')
const { canRecoverMeetingGeneration } = await vite.ssrLoadModule(
  '/src/pages/Meetings/useMeetingReports.ts',
)
const { mergeMeetingAnalysis } = await vite.ssrLoadModule('/src/pages/Meetings/useMeetingDraft.ts')

const template = {
  id: 'builtin-daily-freeform',
  name: '일일보고서',
  owner: '',
  updated: '',
  fields: [
    {
      id: 'body',
      label: '보고서 본문',
      type: 'textarea',
      required: true,
      aiFilled: true,
    },
  ],
}
const generationInput = {
  report_kind: 'daily',
  report_date: '2026-08-31',
  period_start: null,
  period_end: null,
  source_activity_id: null,
  sales_deal_ids: [],
  attachments: [],
  template_snapshot: template,
  content: { values: {}, activities: [] },
  transcript: null,
  guidance: '합성 입력',
}
const run = (status, output = null) => ({
  id: `run-${status}`,
  report_id: null,
  source_refs: { report_kind: 'daily', report_date: '2026-08-31' },
  generation_input: generationInput,
  status_code: status,
  current_stage_code: status,
  attempt_count: 1,
  output_snapshot: output,
  evidence: null,
  error_code: status === 'failed' ? 'synthetic_failure' : null,
  error_message: null,
  created_at: '2026-08-31T00:00:00Z',
})

test('같은 논리 시도의 응답 유실 재시도는 멱등 키를 재사용하고 입력 변경은 새 키를 쓴다', () => {
  const payload = {
    report_kind: 'daily',
    values: { body: 'A', memo: 'B' },
  }
  const first = idempotencyAttemptFor(undefined, payload)
  const retry = idempotencyAttemptFor(first, {
    values: { memo: 'B', body: 'A' },
    report_kind: 'daily',
  })
  const edited = idempotencyAttemptFor(first, {
    report_kind: 'daily',
    values: { body: 'B' },
  })

  assert.equal(retry, first)
  assert.equal(retry.key, first.key)
  assert.notEqual(edited.key, first.key)

  // POST 뒤 polling만 실패한 동안에는 시도를 닫지 않아 같은 run을 다시 받습니다.
  const afterPollingFailure = idempotencyAttemptFor(first, payload)
  assert.equal(afterPollingFailure.key, first.key)
  const finished = finishIdempotencyAttempt(afterPollingFailure, first.key)
  const nextGeneration = idempotencyAttemptFor(finished, payload)
  assert.notEqual(nextGeneration.key, first.key)
  assert.equal(finishIdempotencyAttempt(edited, first.key), edited)
})

test('기간 보고서 복구 polling은 복구 입력으로 화면 상태가 바뀌어도 같은 effect에서 이어진다', async () => {
  const source = await readFile(
    new URL('../src/pages/Daily/useDailyDraft.ts', import.meta.url),
    'utf8',
  )
  const recoveryEffect = source.slice(
    source.indexOf('if (existingLoading || recoveredScope.current === scopeKey)'),
    source.indexOf('useEffect(\n    () => () =>'),
  )
  const dependencies = recoveryEffect.slice(recoveryEffect.lastIndexOf('}, ['))

  assert.match(source, /const resumeGenerationRef = useRef\(resumeGeneration\)/)
  assert.match(recoveryEffect, /resumeGenerationRef\.current\(run, controller\)/)
  assert.match(recoveryEffect, /recoveredScope\.current = ''/)
  assert.doesNotMatch(dependencies, /\bresumeGeneration\b/)
})

test('관련 조회는 생성·제출을 막되 조회 갱신은 본문 초기화나 복구 재실행을 하지 않는다', async () => {
  const source = await readFile(
    new URL('../src/pages/Daily/useDailyDraft.ts', import.meta.url),
    'utf8',
  )
  const canGenerate = source.slice(
    source.indexOf('const canGenerate ='),
    source.indexOf('const acceptGeneration'),
  )
  assert.match(canGenerate, /sourcesReady/)
  assert.match(canGenerate, /hasInput/)
  assert.match(source, /const sourcesReady = !related.loading && !related.error/)
  const resetEffect = source.slice(
    source.indexOf('useEffect(() => {\n    reset()'),
    source.indexOf('const setValue'),
  )
  assert.doesNotMatch(resetEffect, /related|activities/)
  const recovery = source.slice(
    source.indexOf('if (existingLoading || recoveredScope.current'),
    source.indexOf('useEffect(\n    () => () =>'),
  )
  assert.doesNotMatch(recovery.slice(recovery.lastIndexOf('}, [')), /related/)
  const compose = await readFile(new URL('../src/pages/Daily/Compose.tsx', import.meta.url), 'utf8')
  const submit = compose.slice(
    compose.indexOf('const onSubmit ='),
    compose.indexOf('if (isFuture)'),
  )
  assert.match(submit, /draft.missing.length > 0/)
  assert.match(compose, /activities: draft.activities/)
})

test('복구 출처 비교는 추가·정렬·표시 변경을 허용하고 참조·포함·제출본 누락은 감지한다', async () => {
  const { generationSourcesAreAvailable } = await vite.ssrLoadModule(
    '/src/pages/Daily/useDailyDraft.ts',
  )
  const first = {
    id: 'a',
    source: '업무보고서',
    refId: 'a',
    included: true,
    sourceSubmissionId: 'v1',
  }
  const second = { ...first, id: 'b', refId: 'b' }
  const frozen = [first, second, { ...first, refId: 'excluded', included: false }]
  assert.equal(
    generationSourcesAreAvailable(frozen, [
      second,
      { ...first, title: '새 제목' },
      { ...first, refId: 'new' },
    ]),
    true,
  )
  for (const changes of [
    { refId: 'other' },
    { source: '일일보고서' },
    { included: false },
    { sourceSubmissionId: 'v2' },
    { sourceSubmissionId: undefined },
  ]) {
    assert.equal(generationSourcesAreAvailable(frozen, [{ ...first, ...changes }, second]), false)
  }
  assert.equal(generationSourcesAreAvailable(frozen, [second]), false)
  assert.equal(generationSourcesAreAvailable([], [first]), true)
})

test('보고서 첨부 API는 파일을 multipart로 올리고 일회용 추출 객체를 받는다', async () => {
  const originalAdapter = client.defaults.adapter
  const calls = []
  const file = new File(['synthetic'], 'meeting.mp3', { type: 'audio/mpeg' })
  client.defaults.adapter = async (config) => {
    calls.push(config)
    return {
      data: {
        id: '30000000-0000-4000-8000-000000000001',
        kind: 'audio',
        name: file.name,
        byte_size: file.size,
        extract: '합성 전사',
      },
      status: 201,
      statusText: 'OK',
      headers: {},
      config,
    }
  }
  try {
    assert.deepEqual(await uploadReportAttachment(file), {
      id: '30000000-0000-4000-8000-000000000001',
      kind: 'audio',
      name: file.name,
      byte_size: file.size,
      extract: '합성 전사',
    })
  } finally {
    client.defaults.adapter = originalAdapter
  }

  assert.equal(calls[0].url, '/report-attachments')
  assert.equal(calls[0].timeout, 300_000)
  assert.equal(calls[0].data.get('upload'), file)
  assert.equal(calls.length, 1)
})

test('첨부 형식 판별은 MIME이 비어도 서버 허용 확장자를 사용한다', () => {
  assert.equal(kindOf(new File([], 'voice.M4A')), 'audio')
  assert.equal(kindOf(new File([], 'photo.jpeg')), 'image')
  assert.equal(kindOf(new File([], 'brief.pdf')), 'pdf')
  assert.equal(kindOf(new File([], 'animation.gif', { type: 'image/gif' })), null)
  assert.equal(kindOf(new File([], 'notes.txt')), null)
})

test('첨부 훅은 업로드 중 제거된 파일의 늦은 응답을 되살리지 않는다', async () => {
  const source = await readFile(new URL('../src/shared/useAttachments.ts', import.meta.url), 'utf8')

  assert.equal(REPORT_ATTACHMENT_LIMIT, 10)
  assert.match(source, /REPORT_ATTACHMENT_LIMIT - current\.current\.length/)
  assert.match(source, /uploadReportAttachment\(file\)/)
  assert.match(
    source,
    /!mounted\.current \|\|[\s\S]*?!current\.current\.some\(\(attachment\) => attachment\.id === item\.id\)[\s\S]*?return/,
  )
  assert.match(
    source,
    /pending: attachments\.some\(\(attachment\) => attachment\.state === 'analyzing'\)/,
  )
  assert.doesNotMatch(source, /onTranscribed|pendingCount/)
  assert.doesNotMatch(source, /deleteReportAttachment|attachment_file_ids/)
  assert.doesNotMatch(source, /transcribeAudio/)
})

test('미팅 복구 입력이 현재 일정과 다르면 오류 배너 없이 복구 대상에서 제외한다', async () => {
  const source = await readFile(
    new URL('../src/pages/Meetings/Compose.tsx', import.meta.url),
    'utf8',
  )

  assert.match(source, /reason\.message === 'report_generation_input_missing'/)
  assert.match(source, /!missingInput/)
  assert.match(
    source,
    /meetingAttachmentPurposeOf\(attachment\) === 'meeting_source' && attachment\.extract\.trim\(\)/,
  )
  assert.match(source, /\(!input\.transcript\?\.trim\(\) && !hasSource\)/)
  assert.match(
    source,
    /\.finally\(\(\) => \{[\s\S]*?recoveryAbort\.current = null[\s\S]*?setRecovering\(false\)/,
  )
})

test('미팅 원문·첨부·선택 딜 변경은 이전 생성 run을 제출에서 제외한다', async () => {
  const source = await readFile(
    new URL('../src/pages/Meetings/useMeetingDraft.ts', import.meta.url),
    'utf8',
  )

  assert.match(source, /const changeTranscript[\s\S]*?invalidateGeneration\(\)/)
  assert.match(source, /const toggleSalesDeal[\s\S]*?invalidateGeneration\(\)/)
  assert.match(source, /const addAttachments[\s\S]*?invalidateGeneration\(\)/)
  assert.match(source, /const removeAttachment[\s\S]*?invalidateGeneration\(\)/)
  assert.match(source, /const setAttachmentExtract[\s\S]*?invalidateGeneration\(\)/)
  assert.match(source, /setTranscript: changeTranscript/)
})

test('기간 작성은 미팅 원문 UI 없이 공통 첨부만 표시한다', async () => {
  const source = await readFile(new URL('../src/pages/Daily/Compose.tsx', import.meta.url), 'utf8')
  assert.match(source, /<AttachmentPanel/)
  assert.doesNotMatch(source, /MeetingInputPanel|<textarea|onTranscriptChange/)
})

test('미팅 첨부 목적이나 교정문이 바뀌면 동결된 생성 입력을 재사용하지 않는다', () => {
  const attachment = {
    id: 'source-1',
    kind: 'image',
    purpose: 'meeting_source',
    name: '원문.jpg',
    byte_size: 1024,
    extract: '실제 기록',
  }
  const input = { ...generationInput, report_kind: 'meeting', attachments: [attachment] }
  const request = { ...input, idempotency_key: 'new-attempt' }
  assert.equal(sameReportGenerationInput(input, request), true)
  for (const changed of [
    { ...attachment, purpose: 'reference' },
    { ...attachment, extract: '교정문' },
  ]) {
    assert.equal(sameReportGenerationInput(input, { ...request, attachments: [changed] }), false)
  }
})

test('첨부 업로드 중에는 기간·미팅 생성과 최종 제출을 시작하지 않는다', async () => {
  const [dailyDraft, dailyCompose, meetingDraft, meetingCompose] = await Promise.all([
    readFile(new URL('../src/pages/Daily/useDailyDraft.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/pages/Daily/Compose.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/pages/Meetings/useMeetingDraft.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/pages/Meetings/Compose.tsx', import.meta.url), 'utf8'),
  ])

  assert.match(dailyDraft, /attachmentsPending: files\.pending/)
  assert.match(dailyDraft, /setGenerationRunId\(undefined\)[\s\S]*?addFiles\(picked\)/)
  assert.match(dailyDraft, /setGenerationRunId\(undefined\)[\s\S]*?removeFile\(id\)/)
  assert.match(dailyCompose, /if\s*\(\s*draft\.attachmentsPending\s*\|\|/)
  assert.match(dailyCompose, /draft\.recovering \|\|\n\s+draft\.attachmentsPending/)
  assert.match(meetingDraft, /attachmentsPending: files\.pending/)
  assert.match(
    meetingDraft,
    /meetingAttachmentPurposeOf\(attachment\) === 'meeting_source' &&\s+attachment\.state === 'done'/,
  )
  assert.match(meetingCompose, /busy \|\|\n\s+draft\.attachmentsPending \|\|/)
  assert.match(meetingCompose, /aria-busy=\{submitting \|\| draft\.attachmentsPending\}/)
})

test('제출된 보고서는 저장 후 시작한 같은 자료 재생성만 복구한다', async () => {
  const meeting = await readFile(
    new URL('../src/pages/Meetings/Compose.tsx', import.meta.url),
    'utf8',
  )
  const period = await readFile(
    new URL('../src/pages/Daily/useDailyDraft.ts', import.meta.url),
    'utf8',
  )
  const daily = await readFile(new URL('../src/pages/Daily/Compose.tsx', import.meta.url), 'utf8')
  const savedReport = {
    ownerMemberId: 'member-1',
    apiStatus: 'submitted',
    updatedAt: '2026-09-03T06:00:00Z',
    dealSections: [{ salesDealId: 'deal-1' }],
  }
  const regenerated = {
    created_at: '2026-09-03T06:00:01Z',
    status_code: 'completed',
    generation_input: { sales_deal_ids: ['deal-1', 'deal-2'] },
  }

  assert.equal(canRecoverMeetingGeneration(regenerated, savedReport, 'member-1'), true)
  assert.equal(
    canRecoverMeetingGeneration(
      { ...regenerated, created_at: '2026-09-03T05:59:59Z' },
      savedReport,
      'member-1',
    ),
    false,
  )
  assert.equal(
    canRecoverMeetingGeneration(
      { ...regenerated, generation_input: { sales_deal_ids: ['deal-2'] } },
      savedReport,
      'member-1',
    ),
    false,
  )
  assert.equal(
    canRecoverMeetingGeneration({ ...regenerated, status_code: 'failed' }, savedReport, 'member-1'),
    false,
  )
  assert.equal(
    canRecoverMeetingGeneration(regenerated, { ...savedReport, apiStatus: 'approved' }, 'member-1'),
    false,
  )
  assert.match(
    meeting,
    /meetingInputOf\(run, agendaId\)[\s\S]*?canRecoverMeetingGeneration\(run, savedReport, memberId\)[\s\S]*?resumeGeneration\(run, controller\)/,
  )
  assert.match(
    period,
    /periodInputOf\(run, kind, dateISO\)[\s\S]*?canRecoverReportGeneration\(run, canonical, memberId\)[\s\S]*?resumeGenerationRef\.current\(run, controller\)/,
  )
  assert.doesNotMatch(`${meeting}\n${daily}`, /이전에 생성하던 후보|후보 복구/)
})

test('생성·재접속은 AgentRun API만 쓰고 canonical 저장은 finalize 한 번뿐이다', async () => {
  const originalAdapter = client.defaults.adapter
  const calls = []
  client.defaults.adapter = async (config) => {
    calls.push({ method: config.method, url: config.url, params: config.params, data: config.data })
    const data =
      config.url === '/reports/finalize'
        ? { id: 'final-report' }
        : run('completed', { fields: [{ field_id: 'body', value: '완료 본문' }] })
    return { data, status: 200, statusText: 'OK', headers: {}, config }
  }
  try {
    await createReportGeneration({
      idempotency_key: 'generation-key',
      report_kind: 'daily',
      report_date: '2026-08-31',
      attachments: [],
      template_snapshot: template,
      content: generationInput.content,
      guidance: '합성 입력',
    })
    await latestReportGeneration({ report_kind: 'daily', report_date: '2026-08-31' })
    await finalizeReport({ idempotency_key: 'finalize-key' })
  } finally {
    client.defaults.adapter = originalAdapter
  }

  assert.deepEqual(
    calls.map(({ method, url }) => [method, url]),
    [
      ['post', '/report-generations'],
      ['get', '/report-generations/latest'],
      ['post', '/reports/finalize'],
    ],
  )
  assert.deepEqual(calls[1].params, { report_kind: 'daily', report_date: '2026-08-31' })
  assert.equal(
    calls.some(({ url }) => url === '/reports'),
    false,
  )
})

test('POST 성공 뒤 polling이 끊겨도 재시도 요청은 같은 idempotency key로 같은 run을 잇는다', async () => {
  const originalAdapter = client.defaults.adapter
  const input = {
    report_kind: 'daily',
    report_date: '2026-08-31',
    attachments: [],
    template_snapshot: template,
    content: generationInput.content,
    guidance: '합성 입력',
  }
  let attempt = idempotencyAttemptFor(undefined, input)
  const sentKeys = []
  client.defaults.adapter = async (config) => {
    if (config.url === '/report-generations') {
      sentKeys.push(JSON.parse(config.data).idempotency_key)
      return {
        data: run('queued'),
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }
    throw new Error('synthetic_poll_disconnect')
  }
  try {
    const created = await createReportGeneration({ ...input, idempotency_key: attempt.key })
    await assert.rejects(
      waitForReportGeneration(created, undefined, undefined, 0),
      /synthetic_poll_disconnect/,
    )

    attempt = idempotencyAttemptFor(attempt, input)
    await createReportGeneration({ ...input, idempotency_key: attempt.key })
  } finally {
    client.defaults.adapter = originalAdapter
  }

  assert.deepEqual(sentKeys, [attempt.key, attempt.key])
})

test('latest는 queued/running/completed/partial/failed 상태와 복구 입력을 그대로 돌려준다', async () => {
  const originalAdapter = client.defaults.adapter
  try {
    for (const status of ['queued', 'running', 'completed', 'partial', 'failed']) {
      client.defaults.adapter = async (config) => ({
        data: run(status),
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      })
      const latest = await latestReportGeneration({
        report_kind: 'daily',
        report_date: '2026-08-31',
      })
      assert.equal(latest.status_code, status)
      assert.equal(latest.generation_input.guidance, '합성 입력')
    }
  } finally {
    client.defaults.adapter = originalAdapter
  }
})

test('queued/running은 같은 run을 기다리고 completed/partial만 후보로 받으며 failed는 거부한다', async () => {
  const originalAdapter = client.defaults.adapter
  const states = [run('running'), run('completed', { fields: [] })]
  const seen = []
  client.defaults.adapter = async (config) => ({
    data: states.shift(),
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
  })
  try {
    const completed = await waitForReportGeneration(
      run('queued'),
      (status) => seen.push(status),
      undefined,
      0,
    )
    assert.equal(completed.status_code, 'completed')
    assert.deepEqual(seen, ['queued', 'running', 'completed'])

    const partial = await waitForReportGeneration(run('partial', { fields: [] }))
    assert.equal(partial.status_code, 'partial')
    await assert.rejects(waitForReportGeneration(run('failed')), /synthetic_failure/)
  } finally {
    client.defaults.adapter = originalAdapter
  }
})

test('미팅 report retry는 같은 근거만 재사용하고 child 완료·지연 analysis·확정 id를 잇는다', async () => {
  const originalAdapter = client.defaults.adapter
  const input = {
    report_kind: 'meeting',
    report_date: '2026-09-01',
    period_start: null,
    period_end: null,
    source_activity_id: 'agenda-1',
    sales_deal_ids: ['deal-1'],
    template_snapshot: { ...template, name: '미팅' },
    content: {
      transcript: '원문',
      attachments: [{ id: 'attachment-1', kind: 'pdf', extract: '근거' }],
      deals: [{ id: 'deal-1', title: '딜' }],
    },
    transcript: '원문',
    guidance: '합성 미팅 안내',
  }
  const request = { ...input, idempotency_key: 'attempt-1' }
  const parent = (
    reportStatus,
    analysisStatus,
    reportOutput,
    analysisOutput,
    reportId = 'report-child-1',
  ) => ({
    id: 'parent-1',
    agent_code: 'meeting_processing',
    report_id: null,
    source_refs: { parent_run_id: 'parent-1' },
    generation_input: input,
    status_code: 'completed',
    current_stage_code: 'completed',
    attempt_count: 1,
    output_snapshot: {
      evidence: { schema_version: 'meeting_content.v1', selected_deal_ids: ['deal-1'] },
    },
    evidence: null,
    error_code: null,
    error_message: null,
    created_at: '2026-09-01T00:00:00Z',
    child_runs: [
      {
        id: reportId,
        agent_code: 'meeting_report_writing',
        status_code: reportStatus,
        current_stage_code: reportStatus,
        output_snapshot: reportOutput,
        error_code: null,
        error_message: null,
        source_refs: { parent_run_id: 'parent-1' },
        created_at: '2026-09-01T00:00:01Z',
      },
      {
        id: 'analysis-child-1',
        agent_code: 'meeting_analysis',
        status_code: analysisStatus,
        current_stage_code: analysisStatus,
        output_snapshot: analysisOutput,
        error_code: null,
        error_message: null,
        source_refs: { parent_run_id: 'parent-1' },
        created_at: '2026-09-01T00:00:01Z',
      },
    ],
  })
  const reportOutput = {
    deal_reports: [{ sales_deal_id: 'deal-1', title: '제목', body: '본문', evidence_ids: [] }],
    common_report: null,
    unassigned_report: null,
  }
  const analysisOutput = {
    analyses: [
      {
        sales_deal_id: 'deal-1',
        features: { company_size: 'large' },
        assessment: { label: 'high', high_probability: 0.8, model_version: 'test' },
        error: null,
      },
    ],
  }
  const calls = []
  let parentReads = 0
  client.defaults.adapter = async (config) => {
    calls.push({ method: config.method, url: config.url, data: config.data })
    if (config.url === '/report-generations/latest') {
      return {
        data: parent('failed', 'failed', null, null),
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }
    if (config.url === '/agent-runs/report-child-1/retry') {
      return {
        data: {
          ...parent('queued', 'running', null, null),
          id: 'report-child-2',
          agent_code: 'meeting_report_writing',
          source_refs: { parent_run_id: 'parent-1' },
          child_runs: undefined,
          output_snapshot: null,
          status_code: 'queued',
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }
    if (config.url === '/agent-runs/report-child-2') {
      return {
        data: {
          id: 'report-child-2',
          agent_code: 'meeting_report_writing',
          report_id: null,
          source_refs: { parent_run_id: 'parent-1' },
          generation_input: input,
          status_code: 'completed',
          current_stage_code: 'completed',
          attempt_count: 1,
          output_snapshot: reportOutput,
          evidence: null,
          error_code: null,
          error_message: null,
          created_at: '2026-09-01T00:00:01Z',
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }
    if (config.url === '/agent-runs/parent-1') {
      parentReads += 1
      const state = parent('completed', 'running', reportOutput, null, 'report-child-2')
      if (parentReads > 2)
        state.child_runs[1] = {
          ...state.child_runs[1],
          status_code: 'completed',
          output_snapshot: analysisOutput,
        }
      return { data: state, status: 200, statusText: 'OK', headers: {}, config }
    }
    if (config.url === '/reports/finalize') {
      return { data: { id: 'saved-report' }, status: 200, statusText: 'OK', headers: {}, config }
    }
    if (config.url === '/report-generations') {
      return {
        data: {
          ...parent('queued', 'queued', null, null),
          id: 'new-parent-1',
          child_runs: undefined,
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }
    throw new Error(`unexpected ${config.method} ${config.url}`)
  }
  try {
    const latest = await latestMeetingProcessing('agenda-1')
    assert.equal(sameReportGenerationInput(latest.generation_input, request), true)
    assert.equal(
      sameReportGenerationInput(latest.generation_input, {
        ...request,
        content: { ...input.content, attachments: [{ id: 'changed' }] },
      }),
      false,
    )
    const retried = await retryMeetingReport('report-child-1')
    const ready = await waitForMeetingProcessing(retried, undefined, undefined, 0)
    assert.equal(ready.id, 'report-child-2' /* retry child id remains the finalize candidate */)
    assert.equal(ready.source_refs.parent_run_id, 'parent-1')
    assert.equal(ready.output_snapshot.reports.deal_reports[0].body, '본문')

    const analysisStates = []
    await waitForMeetingAnalysis(
      'parent-1',
      (child) => analysisStates.push(child.status_code),
      undefined,
      0,
    )
    assert.deepEqual(analysisStates, ['running', 'completed'])
    const finalized = await finalizeReport({
      idempotency_key: 'finalize-1',
      agent_run_id: ready.id,
    })
    assert.equal(finalized.id, 'saved-report')

    await createReportGeneration({
      ...request,
      idempotency_key: 'attempt-2',
      content: { ...input.content, transcript: '변경' },
    })
  } finally {
    client.defaults.adapter = originalAdapter
  }
  assert.deepEqual(
    calls.map(({ method, url }) => [method, url]),
    [
      ['get', '/report-generations/latest'],
      ['post', '/agent-runs/report-child-1/retry'],
      ['get', '/agent-runs/report-child-2'],
      ['get', '/agent-runs/parent-1'],
      ['get', '/agent-runs/parent-1'],
      ['get', '/agent-runs/parent-1'],
      ['post', '/reports/finalize'],
      ['post', '/report-generations'],
    ],
  )
  assert.equal(JSON.parse(calls.at(-2).data).agent_run_id, 'report-child-2')
})

test('지연 analysis 반영은 사용자가 편집한 보고서 본문을 보존한다', () => {
  const drafts = {
    'deal-1': {
      values: { body: '사용자가 고친 본문' },
      title: '사용자 제목',
      touched: true,
      docKey: 7,
      phase: 'ready',
      statusCode: 'draft',
      review: 'writing',
      reportId: 'report-1',
      reportVersion: 1,
      evidence: '사람 근거',
      generationError: null,
      analysisPhase: 'running',
      assessment: undefined,
      analysisError: null,
    },
  }
  const merged = mergeMeetingAnalysis(drafts, {
    id: 'analysis-child-1',
    agent_code: 'meeting_analysis',
    status_code: 'completed',
    current_stage_code: 'completed',
    output_snapshot: {
      analyses: [
        {
          sales_deal_id: 'deal-1',
          features: { company_size: 'large' },
          assessment: { label: 'watch', high_probability: 0.3, model_version: 'test' },
          error: null,
        },
      ],
    },
    error_code: null,
    error_message: null,
    source_refs: { parent_run_id: 'parent-1' },
    created_at: null,
  })
  assert.equal(merged['deal-1'].values.body, '사용자가 고친 본문')
  assert.equal(merged['deal-1'].title, '사용자 제목')
  assert.equal(merged['deal-1'].touched, true)
  assert.equal(merged['deal-1'].docKey, 7)
  assert.equal(merged['deal-1'].analysisPhase, 'completed')
  assert.equal(merged['deal-1'].assessment.label, 'watch')
})

test('실시간 analysis 내부 오류 코드도 저장 복구와 같은 사용자 문구로 바꾼다', () => {
  const draft = { 'deal-1': { analysisPhase: 'running', analysisError: null } }
  const failedChild = {
    status_code: 'failed',
    error_code: 'meeting_analysis_failed',
    error_message: null,
    output_snapshot: null,
  }
  assert.equal(
    mergeMeetingAnalysis(draft, failedChild)['deal-1'].analysisError,
    '미팅 분석을 완료하지 못했습니다. 다시 시도해 주세요.',
  )
  const failedItem = {
    status_code: 'completed',
    output_snapshot: {
      analyses: [{ sales_deal_id: 'deal-1', assessment: null, error: 'meeting_analysis_failed' }],
    },
  }
  assert.equal(
    mergeMeetingAnalysis(draft, failedItem)['deal-1'].analysisError,
    '미팅 분석을 완료하지 못했습니다. 다시 시도해 주세요.',
  )
})

test('report child 실패도 analysis sibling을 계속 소비하고 report 실패를 유지한다', async () => {
  const originalAdapter = client.defaults.adapter
  const analysisOutput = {
    analyses: [
      {
        sales_deal_id: 'deal-1',
        features: { company_size: 'large' },
        assessment: { label: 'high', high_probability: 0.8, model_version: 'test' },
        error: null,
      },
    ],
  }
  let reads = 0
  const parent = () => ({
    id: 'parent-failed-report',
    agent_code: 'meeting_processing',
    report_id: null,
    source_refs: {},
    generation_input: null,
    status_code: 'completed',
    current_stage_code: 'completed',
    attempt_count: 1,
    output_snapshot: {
      evidence: { schema_version: 'meeting_content.v1', selected_deal_ids: ['deal-1'] },
    },
    evidence: null,
    error_code: null,
    error_message: null,
    created_at: null,
    child_runs: [
      {
        id: 'failed-report-child',
        agent_code: 'meeting_report_writing',
        status_code: 'failed',
        current_stage_code: 'failed',
        output_snapshot: null,
        error_code: 'report_writing_failed',
        error_message: null,
        source_refs: { parent_run_id: 'parent-failed-report' },
        created_at: null,
      },
      {
        id: 'analysis-child',
        agent_code: 'meeting_analysis',
        status_code: reads === 0 ? 'running' : 'completed',
        current_stage_code: reads === 0 ? 'running' : 'completed',
        output_snapshot: reads === 0 ? null : analysisOutput,
        error_code: null,
        error_message: null,
        source_refs: { parent_run_id: 'parent-failed-report' },
        created_at: null,
      },
    ],
  })
  client.defaults.adapter = async (config) => {
    assert.equal(config.url, '/agent-runs/parent-failed-report')
    const data = parent()
    reads += 1
    return { data, status: 200, statusText: 'OK', headers: {}, config }
  }
  try {
    let failedCandidateId
    await assert.rejects(
      waitForMeetingProcessing(parent(), undefined, undefined, 0).then((run) => {
        failedCandidateId = run.id
        return run
      }),
      /agent_run_failed/,
    )
    assert.equal(failedCandidateId, undefined)
    const states = []
    await waitForMeetingAnalysis(
      'parent-failed-report',
      (child) => states.push(child.status_code),
      undefined,
      0,
    )
    assert.deepEqual(states, ['running', 'completed'])
    const merged = mergeMeetingAnalysis(
      {
        'deal-1': {
          values: { body: '사용자 본문' },
          title: '사용자 제목',
          touched: true,
          docKey: 1,
          phase: 'ready',
          statusCode: 'draft',
          review: 'writing',
          generationError: 'report_writing_failed',
          analysisPhase: 'running',
          analysisError: null,
        },
      },
      {
        ...parent().child_runs[1],
        status_code: 'completed',
        output_snapshot: analysisOutput,
      },
    )
    assert.equal(merged['deal-1'].analysisPhase, 'completed')
    assert.equal(merged['deal-1'].generationError, 'report_writing_failed')
    assert.equal(merged['deal-1'].values.body, '사용자 본문')
  } finally {
    client.defaults.adapter = originalAdapter
  }
})

test('보고서 입력 경계는 공백·원문 목적·구분자·이모지·JSON UTF-8 크기를 서버와 같이 센다', () => {
  const attachment = (extract, purpose = 'meeting_source', kind = 'pdf') => ({
    id: 'file',
    kind,
    name: '합성.pdf',
    byte_size: 1,
    extract,
    ...(purpose ? { purpose } : {}),
  })
  const meeting = { report_kind: 'meeting', attachments: [], transcript: '', content: {} }
  assert.equal(reportTextLength('  😀한\n '), 2)
  for (const [prefix, typedTooLong, contentTooLong] of [
    ['\uFEFF', true, true],
    ['\u0085', false, false],
    ['\u001c', true, false],
    ['\u001d', true, false],
    ['\u001e', true, false],
    ['\u001f', true, false],
  ]) {
    const body = prefix + 'a'.repeat(50_000)
    assert.equal(
      reportInputError({ transcript: body }),
      typedTooLong ? 'transcript_too_large' : null,
    )
    assert.equal(reportInputError({ body }), typedTooLong ? 'report_body_too_large' : null)
    assert.equal(
      reportInputError({ content: { values: { body } } }),
      contentTooLong ? 'report_body_too_large' : null,
    )
    assert.equal(
      reportInputError({ title: prefix + 'a'.repeat(254) }),
      typedTooLong ? 'report_title_invalid' : null,
    )
    assert.equal(
      reportInputError({ content: { title: prefix + 'a'.repeat(254) } }),
      contentTooLong ? 'report_title_invalid' : null,
    )
    assert.equal(
      reportInputError({ ...meeting, attachments: [attachment(body)] }),
      typedTooLong ? 'report_attachment_text_too_large' : null,
    )
  }
  assert.equal(
    reportInputError({
      ...meeting,
      transcript: '\u001c',
      attachments: [attachment('a'.repeat(49_998))],
    }),
    'meeting_transcript_too_large',
  )
  assert.equal(reportInputError({ ...meeting, transcript: `  ${'😀'.repeat(50_000)}  ` }), null)
  assert.equal(
    reportInputError({ ...meeting, transcript: '😀'.repeat(50_001) }),
    'transcript_too_large',
  )
  const joined = {
    ...meeting,
    transcript: ' a ',
    attachments: [attachment(` ${'😀'.repeat(49_997)} `)],
  }
  assert.equal(reportInputError(joined), null)
  assert.equal(reportInputError({ ...joined, transcript: 'ab' }), 'meeting_transcript_too_large')
  assert.equal(
    reportInputError({
      ...joined,
      transcript: ' \n ',
      attachments: [attachment('😀'.repeat(50_000))],
    }),
    null,
  )
  assert.equal(
    reportInputError({
      ...meeting,
      transcript: 'a',
      attachments: [attachment('😀'.repeat(50_000), 'reference', 'audio')],
    }),
    null,
  )
  assert.equal(
    reportInputError({
      ...meeting,
      transcript: 'a',
      attachments: [attachment('x'.repeat(50_000), null, 'audio')],
    }),
    'meeting_transcript_too_large',
  )
  assert.equal(
    reportInputError({
      ...meeting,
      transcript: 'a',
      attachments: [attachment('x'.repeat(50_000), null, 'pdf')],
    }),
    null,
  )
  assert.equal(
    reportInputError({ ...meeting, attachments: [attachment('x'.repeat(50_001), 'reference')] }),
    'report_attachment_text_too_large',
  )
  assert.equal(
    reportInputError({
      attachments: Array.from({ length: 11 }, () => attachment('a', 'reference')),
    }),
    'report_attachment_limit_exceeded',
  )
  assert.equal(reportInputError({ guidance: '😀'.repeat(2_000) }), null)
  assert.equal(reportInputError({ guidance: '😀'.repeat(2_001) }), 'guidance_too_large')
  assert.equal(reportInputError({ content: { values: { body: '' } } }), null)
  for (const field of ['body', 'common_body', 'unassigned_body']) {
    assert.equal(reportInputError({ [field]: ` ${'😀'.repeat(50_000)} ` }), null)
    assert.equal(reportInputError({ [field]: '😀'.repeat(50_001) }), 'report_body_too_large')
  }
  assert.equal(
    reportInputError({ deal_sections: [{ body: '😀'.repeat(50_001) }] }),
    'report_body_too_large',
  )
  assert.equal(
    reportInputError({ content: { values: { body: 'x'.repeat(50_001) } } }),
    'report_body_too_large',
  )
  assert.equal(reportInputError({ title: ` ${'😀'.repeat(254)} ` }), null)
  assert.equal(reportInputError({ title: '😀'.repeat(255) }), 'report_title_invalid')
  assert.equal(
    reportInputError({ deal_sections: [{ title: 'x'.repeat(255) }] }),
    'report_title_invalid',
  )
  assert.equal(reportInputError({ content: { title: 'x'.repeat(255) } }), 'report_title_invalid')
  const byteLimit = 256 * 1024
  for (const field of ['template_snapshot', 'content']) {
    const text = '가'.repeat(87_378) + 'aa'
    assert.equal(new TextEncoder().encode(JSON.stringify({ x: text })).length, byteLimit)
    assert.equal(reportInputError({ [field]: { x: text } }), null)
    assert.equal(reportInputError({ [field]: { x: text + 'a' } }), `${field}_too_large`)
  }
  assert.equal(
    reportInputError({ deal_sections: [{ content: { x: 'a'.repeat(byteLimit) } }] }),
    'content_too_large',
  )
  const files = [
    attachment('😀'.repeat(40_000), 'reference'),
    attachment('😀'.repeat(40_000), 'reference'),
  ]
  assert.equal(reportInputError({ attachments: files }), 'attachments_too_large')
  const sources = Array.from({ length: 100 }, (_, index) => ({
    source: '업무보고서',
    refId: `source-${index}`,
    included: true,
  }))
  assert.equal(reportInputError({ content: { activities: sources } }), null)
  assert.equal(
    reportInputError({ content: { activities: [...sources, { source: '수기', included: true }] } }),
    null,
  )
  assert.equal(
    reportInputError({ content: { activities: [...sources, { ...sources[0], included: false }] } }),
    null,
  )
  assert.equal(
    reportInputError({ content: { activities: [...sources, sources[0]] } }),
    'report_source_limit_exceeded',
  )
})

test('생성·최종 HITL 우회 호출도 초과 입력은 POST 0회이며 원문을 변경하지 않는다', async () => {
  const originalAdapter = client.defaults.adapter
  let posts = 0
  client.defaults.adapter = async (config) => {
    posts += 1
    return { data: {}, config, status: 200, statusText: 'OK', headers: {} }
  }
  try {
    const over = '😀'.repeat(50_001)
    for (const request of [
      { transcript: over },
      { content: { values: { body: over } } },
      { attachments: [{ name: '합성.pdf', extract: over }] },
      { template_snapshot: { x: '가'.repeat(90_000) } },
    ]) {
      const original = JSON.stringify(request)
      await assert.rejects(createReportGeneration(request))
      await assert.rejects(finalizeReport(request))
      assert.equal(JSON.stringify(request), original)
    }
    for (const request of [
      { body: over },
      { common_body: over },
      { unassigned_body: over },
      { deal_sections: [{ body: over }] },
      { deal_sections: [{ title: 'x'.repeat(255) }] },
    ])
      await assert.rejects(finalizeReport(request))
    assert.equal(posts, 0)
    await finalizeReport({
      report_kind: 'meeting',
      common_body: '사람이 확인한 본문',
      attachments: [],
    })
    assert.equal(posts, 1)
  } finally {
    client.defaults.adapter = originalAdapter
  }
})

test('일반·terminal·Axios·422의 알려진 코드만 안내하고 검증 원문은 노출하지 않는다', () => {
  const fallback = '요청을 완료하지 못했습니다.'
  const known = 'meeting_transcript_too_large'
  const axiosError = (detail, url = '/report-generations') =>
    new AxiosError('원문을 포함할 수 있는 서버 오류', 'ERR_BAD_REQUEST', { url }, null, {
      status: 422,
      data: { detail },
      headers: {},
      config: { url },
      statusText: 'Invalid',
    })
  for (const error of [
    new Error(known),
    new AgentRunTerminalError(known),
    axiosError(known),
    axiosError([
      {
        type: 'value_error',
        loc: ['body'],
        msg: `Value error, ${known}`,
        input: '비공개 원문',
        ctx: { error: '비공개 원문' },
      },
    ]),
  ]) {
    assert.equal(errorMessage(error, fallback), messageForCode(known, fallback))
  }
  const invalid = (field, type = 'string_too_long') =>
    axiosError(
      [
        {
          type,
          loc: ['body', ...field],
          msg: '전체 원문 포함 금지',
          input: '민감 원문',
          ctx: { given: '민감 원문' },
        },
      ],
      '/reports/finalize',
    )
  for (const field of [
    ['body'],
    ['common_body'],
    ['unassigned_body'],
    ['deal_sections', 0, 'body'],
  ])
    assert.equal(
      errorMessage(invalid(field), fallback),
      messageForCode('report_body_too_large', fallback),
    )
  assert.equal(
    errorMessage(invalid(['deal_sections', 0, 'title']), fallback),
    messageForCode('report_title_invalid', fallback),
  )
  assert.equal(
    errorMessage(invalid(['attachments', 0, 'extract']), fallback),
    messageForCode('report_attachment_text_too_large', fallback),
  )
  assert.equal(
    errorMessage(invalid(['attachments'], 'too_long'), fallback),
    messageForCode('report_attachment_limit_exceeded', fallback),
  )
  for (const error of [
    new Error('unknown_private_message'),
    new AgentRunTerminalError('unknown_private_message'),
    new Error('__proto__'),
    new Error('toString'),
    invalid(['customer', 'body']),
    invalid(['body'], 'string_type'),
    axiosError(
      [{ type: 'string_too_long', loc: ['body', 'body'], msg: '민감 원문' }],
      '/customers',
    ),
    axiosError([{ msg: 'Value error, unknown_private_message', input: '민감 원문' }]),
  ])
    assert.equal(errorMessage(error, fallback), fallback)
  for (const code of [
    'llm_provider_error:401',
    'llm_provider_error:429',
    'llm_request_failed:ReadTimeout',
    'report_generation_timeout',
  ]) {
    assert.notEqual(errorMessage(new AgentRunTerminalError(code), fallback), fallback)
  }
  assert.equal(
    errorMessage(new Error('llm_request_failed:unknown_private_message'), fallback),
    fallback,
  )
})
