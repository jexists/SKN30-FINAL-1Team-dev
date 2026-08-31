import assert from 'node:assert/strict'
import test from 'node:test'

import { mergeGeneratedValues, runDealGeneration } from '../src/pages/Meetings/generatedDraft.ts'

test('AI 초안은 빈 최종본만 채우고 직접 작성본은 보존한다', () => {
  const fields = [
    { id: 'reaction', aiFilled: true },
    { id: 'note', aiFilled: false },
  ]
  const generated = { reaction: '긍정적', note: 'AI 메모' }

  assert.deepEqual(mergeGeneratedValues(fields, { reaction: '', note: '' }, generated, true), {
    reaction: '긍정적',
    note: '',
  })
  assert.deepEqual(
    mergeGeneratedValues(fields, { reaction: '직접 작성', note: '사용자 메모' }, generated, false),
    { reaction: '직접 작성', note: '사용자 메모' },
  )
})

test('딜 잠금은 사전저장·ML 대기·자동저장까지 유지하고 중복 실행을 막는다', async () => {
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

test('딜 생성이 실패해도 잠금을 해제해 재시도할 수 있다', async () => {
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
