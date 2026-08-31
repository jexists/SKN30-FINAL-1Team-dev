import assert from 'node:assert/strict'
import test from 'node:test'

import {
  canReassignEvidence,
  hasPendingAi,
  readMeetingAnalysis,
  runDealGeneration,
  transcriptDigest,
} from '../src/pages/Meetings/generatedDraft.ts'

test('서버가 보존한 사람 본문과 새 AI 원본이 다르면 선택 적용을 안내한다', () => {
  const current = { body: '직접 작성한 본문' }
  assert.equal(hasPendingAi(current, { body: '새 AI 초안' }), true)
  assert.equal(hasPendingAi(current, { body: '직접 작성한 본문' }), false)
  assert.equal(hasPendingAi(current, {}), false)
  assert.equal(hasPendingAi({ note: '기존 양식의 사람 본문' }, { note: '새 AI 본문' }), true)
  assert.deepEqual(current, { body: '직접 작성한 본문' })
})

test('원문 또는 선택 딜이 바뀌면 과거 근거 ID를 재배정하지 않는다', () => {
  assert.equal(canReassignEvidence('원문', '원문', ['a', 'b'], ['b', 'a']), true)
  assert.equal(canReassignEvidence('원문', '바뀐 원문', ['a'], ['a']), false)
  assert.equal(canReassignEvidence('원문', '원문', ['a', 'b'], ['a']), false)
  assert.equal(canReassignEvidence('원문', '원문', ['a', 'b'], ['a', 'c']), false)
  assert.equal(canReassignEvidence('원문', null, ['a'], ['a']), false)
})

test('원문 SHA-256은 원문을 변경 없이 해시하고 편집된 원문을 구분한다', async () => {
  assert.equal(
    await transcriptDigest('abc'),
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
  )
  assert.notEqual(await transcriptDigest('미팅 원문'), await transcriptDigest('미팅 원문 '))
})

test('저장된 ML 태그와 실패 정보를 복원하고 불완전한 결과는 무시한다', () => {
  const assessment = { label: 'high', high_probability: 0.8, model_version: 'test-v1' }
  assert.deepEqual(readMeetingAnalysis({ deal_assessment: assessment }), {
    assessment,
    analysisError: undefined,
    reportError: undefined,
  })
  assert.deepEqual(readMeetingAnalysis({ deal_assessment: null, analysis_error: '분석 실패' }), {
    assessment: undefined,
    analysisError: '분석 실패',
    reportError: undefined,
  })
  assert.equal(
    readMeetingAnalysis({ report_error: '본문 생성 실패' }).reportError,
    '본문 생성 실패',
  )
  assert.equal(readMeetingAnalysis({ deal_assessment: { label: 'high' } }).assessment, undefined)
})

test('미팅 잠금은 사전저장·ML 대기·서버 적용까지 유지하고 중복 실행을 막는다', async () => {
  const active = new Set()
  const notifications = []
  const changed = () => notifications.push([...active])
  const beforeSave = Promise.withResolvers()
  const writing = Promise.withResolvers()
  const analysis = Promise.withResolvers()
  const finalSave = Promise.withResolvers()
  const waitingForAnalysis = Promise.withResolvers()
  const savingFinal = Promise.withResolvers()
  let savedValue = ''

  const run = runDealGeneration(active, 'deal-a', changed, async () => {
    assert.equal(active.has('deal-a'), true)
    await beforeSave.promise
    const value = await writing.promise
    waitingForAnalysis.resolve()
    await analysis.promise
    savingFinal.resolve()
    await finalSave.promise
    savedValue = value
    return true
  })

  assert.deepEqual(notifications, [['deal-a']])
  assert.equal(
    await runDealGeneration(active, 'deal-a', changed, () => assert.fail('중복 실행')),
    false,
  )
  assert.equal(await runDealGeneration(active, 'deal-b', changed, async () => true), true)
  assert.equal(active.has('deal-a'), true)

  beforeSave.resolve()
  writing.resolve('AI 초안')
  await waitingForAnalysis.promise
  assert.equal(active.has('deal-a'), true, 'ML 대기 중 편집·저장을 잠근다')
  analysis.resolve()
  await savingFinal.promise
  assert.equal(active.has('deal-a'), true, '자동저장 중에도 잠금을 유지한다')
  finalSave.resolve()
  assert.equal(await run, true)
  assert.equal(savedValue, 'AI 초안')
  assert.deepEqual([...active], [])
  assert.deepEqual(notifications.at(-1), [])
})

test('미팅 생성이 실패해도 잠금을 해제해 재시도할 수 있다', async () => {
  const active = new Set()
  await assert.rejects(
    runDealGeneration(
      active,
      'deal-a',
      () => {},
      async () => {
        throw new Error('save_failed')
      },
    ),
    /save_failed/,
  )
  assert.equal(active.size, 0)
  assert.equal(
    await runDealGeneration(
      active,
      'deal-a',
      () => {},
      async () => true,
    ),
    true,
  )
})
