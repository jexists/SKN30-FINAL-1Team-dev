import assert from 'node:assert/strict'
import test from 'node:test'
import { AxiosError, CanceledError } from 'axios'

import {
  MEETING_WAIT_MS,
  isRetryableMeetingReadError,
  mergeMeetingProgress,
  readMeetingProgress,
  waitForMeetingRun,
} from '../src/api/meetingStream.ts'

const created = {
  id: 'run-1',
  status_code: 'running',
  output_snapshot: null,
  error_message: null,
  evidence: null,
}
const preview = (body, revision = 1) => ({
  section: 'deal',
  sales_deal_id: 'deal-a',
  body,
  revision,
})
const progress = (body, revision = 1) => ({
  run_id: created.id,
  status_code: 'running',
  stage: 'report_writing',
  previews: [preview(body, revision)],
})
const completed = {
  ...created,
  status_code: 'completed',
  output_snapshot: { reports: '검증된 최종 보고서' },
}

function requestError(status, code = 'ERR_NETWORK') {
  const error = new AxiosError('가상 조회 오류', code)
  if (status !== undefined) error.response = { status }
  return error
}

function fakeStream(t) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'EventSource')
  const streams = []
  class FakeEventSource extends EventTarget {
    closed = false
    onerror = null
    constructor(url, options) {
      super()
      this.url = url
      this.options = options
      streams.push(this)
    }
    emit(type, data) {
      const event = new MessageEvent(type, { data: JSON.stringify(data) })
      this.dispatchEvent(event)
      if (type === 'error') this.onerror?.(event)
    }
    close() {
      this.closed = true
    }
  }
  Object.defineProperty(globalThis, 'EventSource', { configurable: true, value: FakeEventSource })
  t.after(() => {
    if (previous) Object.defineProperty(globalThis, 'EventSource', previous)
    else delete globalThis.EventSource
  })
  return streams
}

test('진행 메시지는 현재 실행·정상 preview만 허용하고 저장 필드를 받지 않는다', () => {
  assert.equal(readMeetingProgress(progress('초안'), 'run-other'), null)
  assert.equal(
    readMeetingProgress({ ...progress('초안'), previews: [preview('초안', -1)] }, created.id),
    null,
  )
  assert.equal(readMeetingProgress({ ...progress('초안'), previews: [null] }, created.id), null)
  const parsed = readMeetingProgress(
    {
      ...progress('초안'),
      values: { body: '잘못된 저장값' },
      output_snapshot: completed.output_snapshot,
    },
    created.id,
  )
  assert.deepEqual(parsed, progress('초안'))
  assert.equal('values' in parsed, false)
  assert.equal('output_snapshot' in parsed, false)
})

test('같은 revision 스트림/수정 revision은 전체 문장을 교체하고 이전 revision은 되돌리지 않는다', () => {
  const first = progress('긴 초안')
  assert.equal(mergeMeetingProgress(first, progress('더 긴 초안')).previews[0].body, '더 긴 초안')
  const revised = mergeMeetingProgress(first, progress('수정', 2))
  assert.equal(revised.previews[0].body, '수정')
  assert.equal(mergeMeetingProgress(revised, progress('오래된 초안', 1)).previews[0].body, '수정')
  assert.equal(
    mergeMeetingProgress(revised, { ...progress('다른 실행'), run_id: 'other' }),
    revised,
  )
  assert.equal(first.previews[0].body, '긴 초안')
})

test('인증 스트림은 현재 run만 표시하고 완료 output만 저장 호출부로 반환한다', async (t) => {
  const streams = fakeStream(t)
  const seen = []
  let applied
  const waiting = waitForMeetingRun(created, {
    eventsUrl: '/api/agent-runs/run-1/events',
    readRun: () => assert.fail('정상 스트림에서 중복 조회'),
    onProgress: (event) => seen.push(event),
  }).then((run) => {
    applied = run.output_snapshot
    return run
  })
  const stream = streams[0]
  assert.deepEqual(stream.options, { withCredentials: true })
  stream.emit('progress', { ...progress('이전 실행'), run_id: 'other' })
  stream.emit('progress', progress('검토 전 초안'))
  assert.equal(seen.length, 1)
  assert.equal(applied, undefined)
  stream.emit('done', { ...completed, id: 'other' })
  assert.equal(stream.closed, false)
  stream.emit('done', completed)
  assert.deepEqual((await waiting).output_snapshot, completed.output_snapshot)
  assert.deepEqual(applied, completed.output_snapshot)
  assert.equal(stream.closed, true)
  stream.emit('progress', progress('늦게 도착한 문장'))
  assert.equal(seen.length, 1)
})

test('초안 뒤 실행이 실패해도 초안은 완료·저장 결과로 승격되지 않는다', async (t) => {
  const streams = fakeStream(t)
  let applied = false
  const waiting = waitForMeetingRun(created, {
    eventsUrl: '/events',
    readRun: () => assert.fail('불필요한 조회'),
  }).then(() => {
    applied = true
  })
  streams[0].emit('progress', progress('그럴듯하지만 검토 실패한 초안'))
  streams[0].emit('done', { ...created, status_code: 'failed', error_message: 'review_failed' })
  await assert.rejects(waiting, /review_failed/)
  assert.equal(applied, false)
  assert.equal(streams[0].closed, true)
})

test('스트림 오류는 새 실행 없이 같은 run 조회로 한 번만 전환한다', async (t) => {
  const streams = fakeStream(t)
  let reads = 0
  const waiting = waitForMeetingRun(created, {
    eventsUrl: '/events',
    readRun: async () => {
      reads += 1
      return completed
    },
  })
  streams[0].onerror(new Event('error'))
  streams[0].onerror(new Event('error'))
  assert.equal((await waiting).id, created.id)
  assert.equal(reads, 1)
  assert.equal(streams.length, 1)
  assert.equal(streams[0].closed, true)
})

test('서버 custom error도 기존 인증 갱신 GET 경로로 전환하고 부분 완료를 반환한다', async (t) => {
  const streams = fakeStream(t)
  const partial = {
    ...completed,
    output_snapshot: { reports: null, analyses: [], errors: { reports: '검토 실패' } },
  }
  let reads = 0
  const waiting = waitForMeetingRun(created, {
    eventsUrl: '/events',
    readRun: async () => {
      reads += 1
      return partial
    },
  })
  streams[0].emit('progress', { ...progress(''), stage: 'starting' })
  streams[0].emit('error', { detail: 'not_authenticated' })
  assert.deepEqual((await waiting).output_snapshot, partial.output_snapshot)
  assert.equal(reads, 1)
  assert.equal(streams[0].closed, true)
})

test('네트워크·요청 timeout·5xx만 재시도하고 권한 오류·취소·불명 오류는 종료한다', () => {
  for (const error of [
    requestError(),
    requestError(undefined, 'ECONNABORTED'),
    requestError(undefined, 'ETIMEDOUT'),
    requestError(500),
    requestError(503),
    requestError(504),
  ]) {
    assert.equal(isRetryableMeetingReadError(error), true)
  }
  for (const error of [
    requestError(400),
    requestError(401),
    requestError(403),
    requestError(404),
    requestError(422),
    requestError(429),
    requestError(undefined, 'ERR_CANCELED'),
    new CanceledError(),
    new DOMException('취소', 'AbortError'),
    new Error('알 수 없는 오류'),
    { response: { status: 503 } },
    null,
  ]) {
    assert.equal(isRetryableMeetingReadError(error), false)
  }
  assert.equal(isRetryableMeetingReadError({ isAxiosError: true, response: { status: 503 } }), true)
})

test('일시 오류는 같은 실행을 2·4·8·10초 최대 간격으로 조회해 복구한다', async (t) => {
  const streams = fakeStream(t)
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const errors = [
    requestError(),
    requestError(undefined, 'ECONNABORTED'),
    requestError(503),
    requestError(500),
    requestError(504),
  ]
  let reads = 0
  const waiting = waitForMeetingRun(created, {
    eventsUrl: '/api/agent-runs/run-1/events',
    readRun: async () => {
      const error = errors[reads++]
      if (error) throw error
      return completed
    },
  })
  streams[0].onerror(new Event('error'))
  await Promise.resolve()
  for (const [index, delay] of [2_000, 4_000, 8_000, 10_000, 10_000].entries()) {
    t.mock.timers.tick(delay - 1)
    assert.equal(reads, index + 1)
    t.mock.timers.tick(1)
    await Promise.resolve()
    assert.equal(reads, index + 2)
  }
  assert.equal((await waiting).id, created.id)
  assert.equal(streams.length, 1)
  assert.equal(streams[0].closed, true)
})

test('권한/존재 오류는 폴링을 반복하지 않고 즉시 종료한다', async (t) => {
  const streams = fakeStream(t)
  let reads = 0
  for (const status of [401, 403, 404]) {
    const error = requestError(status)
    const waiting = waitForMeetingRun(created, {
      eventsUrl: '/events',
      readRun: async () => {
        reads += 1
        throw error
      },
    })
    streams.at(-1).onerror(new Event('error'))
    await assert.rejects(waiting, (caught) => caught === error)
  }
  assert.equal(reads, 3)
})

test('재시도 대기 중 화면 이탈은 타이머와 후속 조회를 취소한다', async (t) => {
  const streams = fakeStream(t)
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const controller = new AbortController()
  let reads = 0
  const waiting = waitForMeetingRun(created, {
    eventsUrl: '/events',
    signal: controller.signal,
    readRun: async () => {
      reads += 1
      throw requestError()
    },
  })
  streams[0].onerror(new Event('error'))
  await Promise.resolve()
  controller.abort()
  await assert.rejects(waiting, { name: 'AbortError' })
  t.mock.timers.tick(MEETING_WAIT_MS)
  assert.equal(reads, 1)
})

test('일시 오류 재시도도 처음 정한 25분 제한을 늘리지 않는다', async (t) => {
  const streams = fakeStream(t)
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let reads = 0
  const waiting = waitForMeetingRun(created, {
    eventsUrl: '/events',
    readRun: async () => {
      reads += 1
      throw requestError(503)
    },
  })
  streams[0].onerror(new Event('error'))
  await Promise.resolve()
  t.mock.timers.tick(MEETING_WAIT_MS)
  await assert.rejects(waiting, /agent_run_timeout/)
  const finalReads = reads
  t.mock.timers.tick(MEETING_WAIT_MS)
  await Promise.resolve()
  assert.equal(reads, finalReads)
})

test('화면 이탈은 스트림을 닫고 후속 적용을 취소한다', async (t) => {
  const streams = fakeStream(t)
  const controller = new AbortController()
  const waiting = waitForMeetingRun(created, {
    eventsUrl: '/events',
    signal: controller.signal,
    readRun: () => assert.fail('취소 후 조회'),
  })
  controller.abort()
  await assert.rejects(waiting, { name: 'AbortError' })
  assert.equal(streams[0].closed, true)
})

test('기존 6분을 넘겨도 대기하고 총 25분에서 스트림을 정리한다', async (t) => {
  const streams = fakeStream(t)
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const waiting = waitForMeetingRun(created, {
    eventsUrl: '/events',
    readRun: () => assert.fail('정상 연결 중 조회'),
  })
  assert.equal(MEETING_WAIT_MS, 25 * 60 * 1_000)
  t.mock.timers.tick(6 * 60 * 1_000)
  assert.equal(streams[0].closed, false)
  t.mock.timers.tick(MEETING_WAIT_MS - 6 * 60 * 1_000)
  await assert.rejects(waiting, /agent_run_timeout/)
  assert.equal(streams[0].closed, true)
})
