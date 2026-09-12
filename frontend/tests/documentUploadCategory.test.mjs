import assert from 'node:assert/strict'
import test from 'node:test'

const { categoryFromFileName } = await import('../src/pages/Documents/catalog.ts')

const TRADE = ['견적서', '계약서', '발주서']

test('파일명에서 읽어 낸 분류를 돌려준다', () => {
  assert.equal(categoryFromFileName('계약서 샘플_16.pdf', TRADE), '계약서')
  assert.equal(categoryFromFileName('2026 견적.pdf', TRADE), '견적서')
})

test('파일명에 단서가 없으면 값을 내지 않는다(고른 분류가 기타로 튀지 않는다)', () => {
  assert.equal(categoryFromFileName('a.pdf', TRADE), null)
})

test('이 방에서 고를 수 없는 분류도 값을 내지 않는다', () => {
  // 영업자료실에서 상품 연결이 아니면 기타만 고를 수 있습니다.
  assert.equal(categoryFromFileName('계약서.pdf', ['기타']), null)
  assert.equal(categoryFromFileName('상품 설명서.pdf', ['상품설명서', '기타']), '상품설명서')
})
