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
  waitForReportGeneration,
} = await vite.ssrLoadModule('/src/api/reportAgent.ts')
const { client } = await vite.ssrLoadModule('/src/api/client.ts')
const { uploadReportAttachment } = await vite.ssrLoadModule('/src/api/reportAttachments.ts')
const { kindOf } = await vite.ssrLoadModule('/src/shared/useAttachments.ts')
const { canRecoverMeetingGeneration } = await vite.ssrLoadModule(
  '/src/pages/Meetings/useMeetingReports.ts',
)

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
