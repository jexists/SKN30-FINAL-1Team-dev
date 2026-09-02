import assert from 'node:assert/strict'
import test from 'node:test'

const { pollSummary } = await import('../src/api/polling.ts')

function fakeClock() {
  let current = 0
  return {
    now: () => current,
    sleep: async (milliseconds) => {
      current += milliseconds
    },
  }
}

test('35초 지연 중에도 완료 상태까지 계속 확인한다', async () => {
  const clock = fakeClock()
  let started = false
  let reads = 0

  const result = await pollSummary({
    start: async () => {
      started = true
    },
    read: async () => {
      reads += 1
      return clock.now() < 35_000
        ? { processing_status: 'processing' }
        : { processing_status: 'completed' }
    },
    timeoutMs: 60_000,
    now: clock.now,
    sleep: clock.sleep,
  })

  assert.equal(started, true)
  assert.equal(result.processing_status, 'completed')
  assert.equal(clock.now(), 35_000)
  assert.equal(reads, 36)
})

test('실패 상태를 오류로 전달한다', async () => {
  const clock = fakeClock()
  let reads = 0

  await assert.rejects(
    pollSummary({
      start: async () => undefined,
      read: async () => {
        reads += 1
        return reads === 1
          ? { processing_status: 'processing' }
          : { processing_status: 'failed', processing_error: 'runpod_poll_timeout' }
      },
      now: clock.now,
      sleep: clock.sleep,
    }),
    { message: 'runpod_poll_timeout' },
  )
  assert.equal(reads, 2)
})

test('완료되지 않은 상태가 제한시간을 넘으면 시간초과를 반환한다', async () => {
  const clock = fakeClock()

  await assert.rejects(
    pollSummary({
      start: async () => undefined,
      read: async () => ({ processing_status: 'processing' }),
      timeoutMs: 3_000,
      now: clock.now,
      sleep: clock.sleep,
    }),
    { message: 'document_summary_timeout' },
  )
})
