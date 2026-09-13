import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = await readFile(
  new URL('../src/pages/Dashboard/useAiBriefing.ts', import.meta.url),
  'utf8',
)

test('미팅 상세는 브리핑 실행을 만들지 않고 저장된 결과만 조회한다', () => {
  assert.doesNotMatch(source, /client\.post\(['"]\/agent-runs/)
  assert.match(source, /client\.get<ActivityRead>/)
})

test('게시 상태가 아니라 refreshing으로 5초 간격 재조회한다', () => {
  assert.match(source, /const POLL_INTERVAL_MS = 5_000/)
  assert.match(source, /while \(current\?\.refreshing === true\)/)
  assert.doesNotMatch(source, /status === ['"]queued['"]|status === ['"]running['"]/)
})

test('화면을 닫으면 진행 요청과 재조회 타이머를 취소한다', () => {
  assert.match(source, /new AbortController\(\)/)
  assert.match(source, /signal: controller\.signal/)
  assert.match(source, /window\.clearTimeout\(timer\)/)
  assert.match(source, /controller\.abort\(\)/)
})
