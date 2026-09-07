import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { after, test } from 'node:test'
import { createServer } from 'vite'

const vite = await createServer({
  server: { middlewareMode: true, hmr: { port: 24679 } },
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
    source.indexOf('if (existingLoading || sourcesLoading || recoveredScope.current === scopeKey)'),
    source.indexOf('useEffect(\n    () => () =>'),
  )
  const dependencies = recoveryEffect.slice(recoveryEffect.lastIndexOf('}, ['))

  assert.match(source, /const resumeGenerationRef = useRef\(resumeGeneration\)/)
  assert.match(recoveryEffect, /resumeGenerationRef\.current\(run, controller\)/)
  assert.match(recoveryEffect, /recoveredScope\.current = ''/)
  assert.doesNotMatch(dependencies, /\bresumeGeneration\b/)
})

test('기간 보고서 초기화와 자료 병합은 자료 조회가 끝난 뒤에만 실행한다', async () => {
  const source = await readFile(
    new URL('../src/pages/Daily/useDailyDraft.ts', import.meta.url),
    'utf8',
  )

  assert.match(
    source,
    /useEffect\(\(\) => \{\n    if \(sourcesLoading\) return\n    reset\(\)\n  \}, \[reset, sourcesLoading\]\)/,
  )
  assert.match(source, /if \(sourcesLoading \|\| sourceSelectionFrozen\.current\) return/)
  assert.match(
    source,
    /if \(existingLoading \|\| sourcesLoading \|\| recoveredScope\.current === scopeKey\) return/,
  )
  assert.match(source, /Boolean\(values\.body\?\.trim\(\)\)/)
  assert.match(
    source,
    /const canGenerate = !recovering && !files\.pending && hasAiFields && hasInput/,
  )
  assert.match(source, /if \(!hasInput\) reasons\.push\('자료 1건 이상'\)/)
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

  assert.match(source, /const MAX_ATTACHMENTS = 10/)
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
  assert.match(source, /attachment\.kind === 'audio' && attachment\.extract\.trim\(\)/)
  assert.match(source, /\(!input\.transcript && !hasAudio\)/)
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
  assert.match(source, /setTranscript: changeTranscript/)
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
  assert.match(dailyCompose, /if \(draft\.attachmentsPending\) return/)
  assert.match(dailyCompose, /draft\.recovering \|\|\n\s+draft\.attachmentsPending/)
  assert.match(meetingDraft, /attachmentsPending: files\.pending/)
  assert.match(meetingDraft, /attachment\.kind === 'audio' && attachment\.state === 'done'/)
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
