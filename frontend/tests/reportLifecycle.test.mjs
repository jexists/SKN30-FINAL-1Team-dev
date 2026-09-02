import assert from 'node:assert/strict'
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
  requiresRecoveryConfirmation,
  waitForReportGeneration,
} = await vite.ssrLoadModule('/src/api/reportAgent.ts')
const { client } = await vite.ssrLoadModule('/src/api/client.ts')

const template = {
  id: 'template-1',
  name: '합성 양식',
  owner: '합성',
  updated: '',
  fields: [{ id: 'summary', label: '요약', type: 'textarea', aiFilled: true }],
}
const generationInput = {
  report_kind: 'daily',
  report_date: '2026-08-31',
  period_start: null,
  period_end: null,
  source_activity_id: null,
  sales_deal_ids: [],
  template_snapshot: template,
  content: { values: {}, activities: [], attachments: [] },
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
  const first = idempotencyAttemptFor(undefined, { report_kind: 'daily', values: { body: 'A' } })
  const retry = idempotencyAttemptFor(first, {
    report_kind: 'daily',
    values: { body: 'A' },
  })
  const edited = idempotencyAttemptFor(first, {
    report_kind: 'daily',
    values: { body: 'B' },
  })

  assert.equal(retry, first)
  assert.equal(retry.key, first.key)
  assert.notEqual(edited.key, first.key)

  // POST 뒤 polling만 실패한 동안에는 시도를 닫지 않아 같은 run을 다시 받습니다.
  const afterPollingFailure = idempotencyAttemptFor(first, {
    report_kind: 'daily',
    values: { body: 'A' },
  })
  assert.equal(afterPollingFailure.key, first.key)
  const finished = finishIdempotencyAttempt(afterPollingFailure, first.key)
  const nextGeneration = idempotencyAttemptFor(finished, {
    report_kind: 'daily',
    values: { body: 'A' },
  })
  assert.notEqual(nextGeneration.key, first.key)
  assert.equal(finishIdempotencyAttempt(edited, first.key), edited)
})

test('재접속 후보는 canonical 보고서가 없을 때만 자동 적용한다', () => {
  assert.equal(requiresRecoveryConfirmation(undefined), false)
  assert.equal(requiresRecoveryConfirmation('changes-requested-report'), true)
  assert.equal(requiresRecoveryConfirmation('legacy-draft-report'), true)
})

test('생성·재접속은 AgentRun API만 쓰고 canonical 저장은 finalize 한 번뿐이다', async () => {
  const originalAdapter = client.defaults.adapter
  const calls = []
  client.defaults.adapter = async (config) => {
    calls.push({ method: config.method, url: config.url, params: config.params, data: config.data })
    const data =
      config.url === '/reports/finalize'
        ? { id: 'final-report' }
        : run('completed', { fields: [{ field_id: 'summary', value: '완료' }] })
    return { data, status: 200, statusText: 'OK', headers: {}, config }
  }
  try {
    await createReportGeneration({
      idempotency_key: 'generation-key',
      report_kind: 'daily',
      report_date: '2026-08-31',
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
