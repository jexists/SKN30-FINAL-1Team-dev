import assert from 'node:assert/strict'
import test from 'node:test'

import {
  BLOCK_MS,
  CHARS_PER_TICK,
  CHIP_MS,
  PIECE_MS,
  SENTENCE_MS,
  START,
  TICK_MS,
  advance,
  revealSteps,
  revealView,
  sentenceEnds,
} from '../src/pages/Dashboard/components/RecordDrawer/briefingReveal.ts'

const view = {
  blocks: [
    {
      title: '단가 재검토 요청을 닫으세요',
      body: 'A사가 단가 재검토를 요청했습니다. 이번 미팅에서 기준을 정해야 합니다.',
      actions: ['재검토 기준을 확인합니다.', '승인 절차를 공유합니다.'],
    },
    { title: '', body: '납기 일정이 아직 열려 있습니다.', actions: [] },
  ],
  risks: ['가격 민감', '일정 지연'],
  missingInformation: ['예산 범위'],
}

test('조각은 제목→본문→제안→다음 블록→위험→확인 정보 순서로 펴지고 빈 글은 빠진다', () => {
  const steps = revealSteps(view)
  assert.deepEqual(
    steps.map(
      (step) => `${step.kind}${step.kind === 'risk' || step.kind === 'missing' ? '' : step.block}`,
    ),
    ['title0', 'body0', 'action0', 'action0', 'body1', 'risk', 'risk', 'missing'],
  )
  // 두 번째 블록은 제목이 비어 조각이 없습니다.
  assert.equal(steps.filter((step) => step.kind === 'title').length, 1)
})

test('문장 끝만 쉬는 자리가 되고 글 전체의 끝은 들어가지 않는다', () => {
  const body = view.blocks[0].body
  const ends = sentenceEnds(body)
  assert.equal(ends.length, 1)
  assert.equal(body.slice(0, ends[0]), 'A사가 단가 재검토를 요청했습니다. ')
  assert.deepEqual(sentenceEnds('문장 부호가 없는 글'), [])
})

test('advance 는 글자를 다 치고 조각을 다 소진한 뒤 null 로 끝난다', () => {
  const steps = revealSteps(view)
  let state = START
  let ticks = 0
  for (let next = advance(steps, state); next; next = advance(steps, state)) {
    state = next.state
    ticks += 1
    assert.ok(ticks < 10_000, '끝나지 않는 전이')
  }
  assert.equal(state.step, steps.length)
  const typedChars = steps
    .filter((step) => step.kind !== 'risk')
    .reduce((sum, step) => sum + Math.ceil(step.text.length / CHARS_PER_TICK), 0)
  // 글자 틱 + 조각을 넘기는 전이(조각 수)만큼입니다.
  assert.equal(ticks, typedChars + steps.length)
})

test('간격은 글자·문장 끝·덩어리 경계·알약이 서로 다르다', () => {
  const steps = revealSteps(view)
  const bodyStep = steps.findIndex((step) => step.kind === 'body' && step.block === 0)
  const body = steps[bodyStep].text
  // 글자를 치는 중
  assert.equal(advance(steps, { step: bodyStep, chars: 2 }).delay, TICK_MS)
  // 문장이 끝난 자리
  assert.equal(advance(steps, { step: bodyStep, chars: sentenceEnds(body)[0] }).delay, SENTENCE_MS)
  // 본문을 다 치면 같은 덩어리의 제안이 붙습니다
  assert.equal(advance(steps, { step: bodyStep, chars: body.length }).delay, PIECE_MS)
  // 목록 줄도 글자 단위로 쳐지고, 다 치면 같은 덩어리의 다음 줄이 붙습니다
  const firstAction = steps.findIndex((step) => step.kind === 'action')
  assert.equal(advance(steps, { step: firstAction, chars: 2 }).delay, TICK_MS)
  assert.equal(
    advance(steps, { step: firstAction, chars: steps[firstAction].text.length }).delay,
    PIECE_MS,
  )
  // 블록이 바뀌는 자리
  const lastAction = steps.findLastIndex((step) => step.kind === 'action')
  assert.equal(
    advance(steps, { step: lastAction, chars: steps[lastAction].text.length }).delay,
    BLOCK_MS,
  )
  // 위험 알약끼리
  const firstRisk = steps.findIndex((step) => step.kind === 'risk')
  assert.equal(advance(steps, { step: firstRisk, chars: 0 }).delay, CHIP_MS)
  // 앞 블록의 본문을 다 친 뒤 위험 묶음으로 넘어가는 자리도 덩어리 경계입니다.
  const beforeRisk = steps[firstRisk - 1]
  assert.equal(
    advance(steps, { step: firstRisk - 1, chars: beforeRisk.text.length }).delay,
    BLOCK_MS,
  )
})

test('revealView 는 앞은 전부·현재는 친 만큼·뒤는 아무것도 주지 않는다', () => {
  const steps = revealSteps(view)
  const bodyStep = steps.findIndex((step) => step.kind === 'body' && step.block === 0)
  const shown = revealView(steps, { step: bodyStep, chars: 5 })
  assert.equal(shown.blocks.length, 1)
  assert.deepEqual(shown.blocks[0].title, { text: view.blocks[0].title, done: true })
  assert.deepEqual(shown.blocks[0].body, { text: view.blocks[0].body.slice(0, 5), done: false })
  assert.equal(shown.blocks[0].actions.length, 0)
  assert.equal(shown.risks, 0)
  assert.equal(shown.missing.length, 0)
  assert.equal(shown.done, false)

  const all = revealView(steps, { step: steps.length, chars: 0 })
  assert.equal(all.blocks.length, 2)
  assert.deepEqual(
    all.blocks[0].actions,
    view.blocks[0].actions.map((action) => ({ text: action, done: true })),
  )
  assert.deepEqual(all.blocks[1].body, { text: view.blocks[1].body, done: true })
  assert.equal(all.risks, 2)
  assert.deepEqual(all.missing, [{ text: view.missingInformation[0], done: true }])
  assert.equal(all.done, true)
})

test('치는 중인 줄은 한 번에 하나뿐이고 그 줄만 done 이 아니다', () => {
  const steps = revealSteps(view)
  const missingStep = steps.findIndex((step) => step.kind === 'missing')
  const shown = revealView(steps, { step: missingStep, chars: 3 })
  const lines = [
    ...shown.blocks.flatMap((block) => [block.title, block.body, ...block.actions]),
    ...shown.missing,
  ]
  assert.deepEqual(
    lines.filter((line) => !line.done),
    [{ text: view.missingInformation[0].slice(0, 3), done: false }],
  )
  // 앞 블록의 제안은 이미 다 서 있고, 위험 알약도 전부 붙었습니다.
  assert.equal(shown.blocks[0].actions.length, 2)
  assert.equal(shown.risks, 2)
})
