import assert from 'node:assert/strict'
import test from 'node:test'

import { mergeGeneratedValues } from '../src/pages/Meetings/generatedDraft.ts'

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
