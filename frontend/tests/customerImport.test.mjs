import assert from 'node:assert/strict'
import test from 'node:test'

import { isSameCustomer } from '../src/pages/Customers/duplicate.ts'
import {
  HEADERS,
  HEADER_MAP,
  REQUIRED,
  toBulkItem,
} from '../src/pages/Customers/importCustomers.ts'

test('템플릿 헤더는 읽을 때 쓰는 열 이름과 같아야 왕복이 된다', () => {
  assert.deepEqual(HEADERS, Object.keys(HEADER_MAP))
  // 필수 열이 템플릿에 없으면 받아 채워도 업로드에서 막힌다.
  for (const field of Object.keys(REQUIRED)) {
    assert.ok(
      HEADERS.some((header) => HEADER_MAP[header] === field),
      field,
    )
  }
})

test('읽어 낸 줄은 줄 번호를 달고 일괄 등록이 받는 모양이 된다', () => {
  const item = toBulkItem(3, {
    org: 'ABC회사',
    businessNo: '123-45-67890',
    name: '홍길동',
    phone: '010-1234-5678',
    dept: '영업팀',
    title: '팀장',
    email: 'hong@abc.co.kr',
    visited: '방문',
    memo: '메모',
  })

  assert.deepEqual(item, {
    row: 3,
    company_name: 'ABC회사',
    business_no: '123-45-67890',
    name: '홍길동',
    department: '영업팀',
    job_title: '팀장',
    email: 'hong@abc.co.kr',
    phone: '010-1234-5678',
    visited: '방문',
    memo: '메모',
  })
})


const existing = {
  contact_id: 'c1',
  company_id: 'k1',
  company_name: 'ABC회사',
  name: '홍길동',
  department: '영업팀',
  job_title: '팀장',
  email: 'hong@abc.co.kr',
  phone: '010-1234-5678',
  memo: null,
  visited: false,
  matched_by: ['phone'],
}

const draft = {
  companyName: 'ABC회사',
  name: '홍길동',
  department: '영업팀',
  jobTitle: '팀장',
  email: 'hong@abc.co.kr',
  phone: '010-1234-5678',
  memo: '',
  visited: false,
}

test('값이 모두 같으면 고칠 것이 없으므로 수정 여부를 묻지 않는다', () => {
  assert.equal(isSameCustomer(draft, existing), true)
  // 비어 있는 칸과 null 은 같은 뜻이다. 이것만으로 물으면 매번 묻게 된다.
  assert.equal(isSameCustomer({ ...draft, memo: '  ' }, existing), true)
  assert.equal(isSameCustomer({ ...draft, name: ' 홍길동 ' }, existing), true)
})

test('한 칸이라도 다르면 그 값으로 고칠지 묻는다', () => {
  assert.equal(isSameCustomer({ ...draft, jobTitle: '부장' }, existing), false)
  assert.equal(isSameCustomer({ ...draft, email: '' }, existing), false)
  assert.equal(isSameCustomer({ ...draft, visited: true }, existing), false)
  assert.equal(isSameCustomer({ ...draft, memo: '새 메모' }, existing), false)
})
