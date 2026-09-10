import assert from 'node:assert/strict'
import test from 'node:test'

import {
  addressHead,
  caretPicksAddress,
  formatAddress,
  readAddressLine,
} from '../src/components/AddressField/addressLine.ts'

const picked = { postcode: '81020', address: '합성시 관계구 세일즈로 20', addressDetail: '' }
const scanned = { postcode: '', address: '서울시 서초구 남부순환로 339길 23', addressDetail: '' }
const empty = { postcode: '', address: '', addressDetail: '' }

test('고른 주소는 우편번호를 괄호에 넣어 한 줄이 된다', () => {
  assert.equal(formatAddress(picked), '(81020) 합성시 관계구 세일즈로 20')
  assert.equal(formatAddress({ ...picked, addressDetail: '3층' }), '(81020) 합성시 관계구 세일즈로 20 3층')
})

test('문서에서 읽어 온 주소는 우편번호가 없어 주소만 선다', () => {
  assert.equal(formatAddress(scanned), '서울시 서초구 남부순환로 339길 23')
  assert.equal(formatAddress(empty), '')
})

test('줄 끝에 이어 친 만큼이 상세주소가 된다', () => {
  const typed = `${formatAddress(picked)} 3층`
  assert.deepEqual(readAddressLine(picked, typed), { ...picked, addressDetail: '3층' })
})

test('상세주소를 지워도 고른 주소는 남는다', () => {
  const filled = { ...picked, addressDetail: '3층' }
  assert.deepEqual(readAddressLine(filled, addressHead(filled)), { ...picked, addressDetail: '' })
})

test('고른 주소를 건드리면 값을 고치지 않고 다시 고르게 한다', () => {
  assert.equal(readAddressLine(picked, '(81020) 합성시 관계'), null)
  assert.equal(readAddressLine(picked, ''), null)
  // 주소가 없으면 상세주소만 적을 데도 없다.
  assert.equal(readAddressLine(empty, '3층'), null)
})

test('커서가 주소 안이면 다시 고르고, 줄 끝이면 상세주소를 적는다', () => {
  const head = addressHead(picked).length
  assert.equal(caretPicksAddress(picked, 0), true)
  assert.equal(caretPicksAddress(picked, head - 1), true)
  assert.equal(caretPicksAddress(picked, head), false)
  assert.equal(caretPicksAddress(picked, head + 2), false)
  // 아직 아무것도 없으면 어디를 눌러도 고르는 자리다.
  assert.equal(caretPicksAddress(empty, 0), true)
})
