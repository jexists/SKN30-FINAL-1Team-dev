import assert from 'node:assert/strict'
import test from 'node:test'

import {
  acknowledgeMeetingGeneration,
  getMeetingGeneration,
  startMeetingGeneration,
} from '../src/pages/Meetings/meetingGenerationStore.ts'
import { dismissToast, getToasts } from '../src/shared/toast.ts'

async function waitFor(read) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const value = read()
    if (value) return value
    await new Promise(setImmediate)
  }
  assert.fail('비동기 실행이 끝나지 않았습니다.')
}

function clearToasts() {
  for (const toast of getToasts()) dismissToast(toast.id)
}

test('화면 구독자가 없어져도 사전저장부터 완료 알림까지 실행한다', async () => {
  clearToasts()
  const agendaId = `agenda-${crypto.randomUUID()}`
  const finish = Promise.withResolvers()
  const saved = { id: 'report-1', salesDealId: 'deal-1' }
  const progress = { phase: 'report_writing', previews: [] }

  assert.equal(
    startMeetingGeneration({
      agendaId,
      dealIds: ['deal-1'],
      execute: async (onProgress, onReportSaved) => {
        onReportSaved(saved)
        onProgress(progress)
        return finish.promise
      },
    }),
    true,
  )
  assert.equal(
    startMeetingGeneration({
      agendaId,
      dealIds: ['deal-1'],
      execute: () => assert.fail('같은 미팅을 중복 실행하면 안 됩니다.'),
    }),
    false,
  )
  assert.deepEqual(getMeetingGeneration(agendaId)?.savedReports, [saved])
  assert.equal(getMeetingGeneration(agendaId)?.progress, progress)

  finish.resolve({ reports: [saved], writingFailed: false, errors: {} })
  const completed = await waitFor(() => {
    const state = getMeetingGeneration(agendaId)
    return state?.status === 'completed' ? state : null
  })
  assert.deepEqual(completed.reports, [saved])
  assert.ok(
    getToasts().some(
      (toast) =>
        toast.persistent &&
        toast.to === `/meetings/new?agenda=${agendaId}` &&
        toast.actionLabel === '보고서 보기',
    ),
  )
  acknowledgeMeetingGeneration(agendaId, completed.requestId)
  assert.equal(getMeetingGeneration(agendaId), null)
  clearToasts()
})

test('실패도 화면 밖에 보관하고 돌아갈 수 있는 오류 알림을 남긴다', async () => {
  clearToasts()
  const agendaId = `agenda-${crypto.randomUUID()}`
  startMeetingGeneration({
    agendaId,
    dealIds: ['deal-1'],
    execute: async (_onProgress, onReportSaved) => {
      onReportSaved({ id: 'report-saved-before-failure', salesDealId: 'deal-1' })
      throw new Error('agent_failed')
    },
  })

  const failed = await waitFor(() => {
    const state = getMeetingGeneration(agendaId)
    return state?.status === 'failed' ? state : null
  })
  assert.equal(failed.error, '미팅 처리를 완료하지 못했습니다.')
  assert.equal(failed.savedReports[0].id, 'report-saved-before-failure')
  assert.ok(
    getToasts().some(
      (toast) =>
        toast.tone === 'error' &&
        toast.persistent &&
        toast.to === `/meetings/new?agenda=${agendaId}` &&
        toast.actionLabel === '실패 확인',
    ),
  )
  clearToasts()
})
