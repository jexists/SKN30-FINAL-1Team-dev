import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { createServer } from 'vite'

// 이 모듈은 문장 끊는 자리를 briefingReveal 에서 가져다 씁니다. 확장자 없는 이웃 import 는
// node 가 풀지 못해, salesSummary 테스트와 같이 vite 를 거쳐 싣습니다.
const vite = await createServer({ server: { middlewareMode: true, hmr: false } })
after(() => vite.close())

const { citedRanges, clipRanges, matchTokens, sentenceRanges } = await vite.ssrLoadModule(
  '/src/pages/Dashboard/components/RecordDrawer/briefingCitations.ts',
)

/** 근거 자료 하나. 실제로는 파일 한 건에서 뽑힌 여러 구절이 함께 옵니다. */
const src = (excerpt, key = 'doc') => ({ key, excerpts: [excerpt] })

/** 형광펜이 실제로 덮은 글. 자리만 보면 어느 문장이 칠해졌는지 읽히지 않습니다. */
function marked(body, ranges) {
  return ranges.map((range) => body.slice(range.start, range.end))
}

test('낱말 자르기는 한 글자와 흔한 말을 버리고 숫자는 남긴다', () => {
  const tokens = matchTokens('검수 완료 후 30일 이내 대금을 지급합니다. 확인 필요')
  assert.ok(tokens.has('검수'))
  assert.ok(tokens.has('30'))
  assert.ok(tokens.has('지급'))
  // 한 글자('후', '일')는 근거가 되지 못하고, 조사와 어미는 잘려 나갑니다.
  assert.ok(!tokens.has('후'))
  // 어느 브리핑에나 나오는 말은 겹쳐도 근거가 아닙니다.
  assert.ok(!tokens.has('확인'))
  assert.ok(!tokens.has('필요'))
})

test('문장 자리는 앞뒤 공백을 빼고 끊긴다', () => {
  const body = '첫 문장입니다. 둘째 문장입니다.\n셋째 문장입니다.'
  assert.deepEqual(marked(body, sentenceRanges(body)), [
    '첫 문장입니다.',
    '둘째 문장입니다.',
    '셋째 문장입니다.',
  ])
})

test('금액·날짜·파일명의 마침표에서는 끊지 않는다', () => {
  // 영업 브리핑에는 문장 부호가 아닌 마침표가 늘 섞여 들어옵니다. 여기서 끊기면
  // 형광펜이 숫자 한가운데서 잘리고, 타자도 거기서 한 박자 쉽니다.
  for (const body of [
    '계약 금액은 12,500.50만원입니다.',
    '납기는 3.10 기준입니다.',
    '단가는 1.5억이고 부가세는 별도입니다.',
    '계약서.pdf 기준으로 잔금을 지급합니다.',
  ]) {
    assert.deepEqual(marked(body, sentenceRanges(body)), [body], body)
  }
  // 마침표 뒤에 공백이 오면 그때는 문장이 끝난 것입니다.
  const two = '계약 금액은 12,500.50만원입니다. 검수 후 지급합니다.'
  assert.deepEqual(marked(two, sentenceRanges(two)), [
    '계약 금액은 12,500.50만원입니다.',
    '검수 후 지급합니다.',
  ])
})

test('원문 구절과 가장 많이 겹치는 문장에만 형광펜을 긋는다', () => {
  const body =
    '이번 미팅에서 설치 공간과 전원 준비 여부를 확인하세요. ' +
    '계약서 기준으로 검수 완료 후 30일 이내에 대금을 지급합니다. ' +
    '고객 담당자가 최근 바뀌었습니다.'
  const excerpt = '제4조 대금 지급: 검수가 완료되면 30일 이내에 대금을 지급한다.'
  assert.deepEqual(marked(body, citedRanges(body, [src(excerpt)])), [
    '계약서 기준으로 검수 완료 후 30일 이내에 대금을 지급합니다.',
  ])
})

test('조사와 어미가 달라도 같은 말로 본다', () => {
  // 브리핑은 원문을 다시 써서 옵니다. '대금'과 '대금을', '지급'과 '지급합니다'가 겹치지
  // 않으면 실제로 인용한 문장을 거의 찾지 못합니다.
  const body =
    '합성병원 초음파 장비 납품 전 협의가 예정되어 있습니다. 계약서에 따라 검수 후 대금을 지급합니다.'
  const excerpt = '제4조 대금 지급: 검수 완료 후 30일 이내 대금을 지급합니다.'
  assert.deepEqual(marked(body, citedRanges(body, [src(excerpt)])), [
    '계약서에 따라 검수 후 대금을 지급합니다.',
  ])
})

test('겹치는 낱말이 모자라면 아무 문장도 칠하지 않는다', () => {
  const body = '고객 담당자가 최근 바뀌었습니다. 다음 방문 일자를 잡아야 합니다.'
  assert.deepEqual(citedRanges(body, [src('제4조 대금 지급: 검수 완료 후 지급한다.')]), [])
})

test('자료마다 문장 하나씩 고르고 한 문장을 두 자료가 나눠 갖지 않는다', () => {
  const body = '계약금은 30%이고 잔금은 70%입니다. 납기는 3월 10일이며 설치는 그 주에 진행합니다.'
  const ranges = citedRanges(body, [
    src('계약금 30%, 잔금 70%로 한다.', '계약서'),
    src('납기일은 3월 10일로 하며 설치를 포함한다.', '발주서'),
  ])
  assert.deepEqual(marked(body, ranges), [
    '계약금은 30%이고 잔금은 70%입니다.',
    '납기는 3월 10일이며 설치는 그 주에 진행합니다.',
  ])
  // 문장 끝 아이콘이 어느 자료를 열지 정해집니다.
  assert.deepEqual(
    ranges.map((range) => range.key),
    ['계약서', '발주서'],
  )
  // 자리는 본문 순서대로 옵니다 — 그려 나갈 때 앞에서부터 잘라 쓰기 때문입니다.
  assert.ok(ranges[0].start < ranges[1].start)
})

test('같은 문장을 두 자료가 가리키면 먼저 온 자료가 가진다', () => {
  const body = '잔금은 검수 완료 후 30일 이내에 지급합니다.'
  const ranges = citedRanges(body, [
    src('잔금은 검수 완료 후 30일 이내 지급한다.', '계약서'),
    src('검수 완료 후 30일 이내 잔금을 지급한다.', '발주서'),
  ])
  // 한 자리에 링크가 둘 달리면 어느 것이 이 문장의 근거인지 읽히지 않습니다.
  assert.equal(ranges.length, 1)
  assert.equal(ranges[0].key, '계약서')
})

test('타자 치는 중에는 아직 친 만큼만 칠하고 링크를 달지 않는다', () => {
  const ranges = [
    { start: 10, end: 20, key: 'a', done: true },
    { start: 30, end: 40, key: 'b', done: true },
  ]
  // 잘린 문장은 done 이 false 라, 그동안 문장 끝 아이콘이 붙지 않습니다.
  assert.deepEqual(clipRanges(ranges, 15), [{ start: 10, end: 15, key: 'a', done: false }])
  assert.deepEqual(clipRanges(ranges, 5), [])
  assert.deepEqual(clipRanges(ranges, 20), [{ start: 10, end: 20, key: 'a', done: true }])
  assert.deepEqual(clipRanges(ranges, 100), ranges)
})

test('본문이 비면 잴 것이 없다', () => {
  assert.deepEqual(citedRanges('', [src('대금 지급 조건')]), [])
  assert.deepEqual(citedRanges('계약금 30%입니다.', [src('')]), [])
})
