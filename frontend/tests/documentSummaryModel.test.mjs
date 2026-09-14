import assert from 'node:assert/strict'
import test from 'node:test'

const { toSummaryModel, parseSummaryMarkdown, isEmptySummary } =
  await import('../src/components/DocumentSummaryView/summaryModel.ts')

/** 서버가 _summary_markdown() 으로 찍는 형식 그대로입니다. */
const MARKDOWN = `## 핵심 요약
포커스바이오솔루션 발주서에는 레이저장비 프로브 4개 품목이 기재되어 있습니다.

## 주요 내용

- LP1000 프로브는 4 EA이며, 단가는 130,000원입니다.
- LP2000 프로브는 13 EA입니다.

## 영업 참고사항

- 프로브 재구매 수요가 확인됩니다.

## 리스크

- 없음
`

test('구조화 payload 를 그대로 읽는다', () => {
  const model = toSummaryModel(
    {
      summary: '발주서입니다.',
      key_points: ['품목이 4개입니다.'],
      sales_relevance: ['재구매 수요가 있습니다.'],
      risk_flags: ['납기일이 없습니다.'],
    },
    MARKDOWN,
  )
  assert.equal(model.lead, '발주서입니다.')
  assert.deepEqual(model.keyPoints, ['품목이 4개입니다.'])
  assert.deepEqual(model.salesRelevance, ['재구매 수요가 있습니다.'])
  assert.deepEqual(model.riskFlags, ['납기일이 없습니다.'])
})

test('extracted_fields 는 화면에 세우지 않으므로 모델에 담지 않는다', () => {
  const model = toSummaryModel(
    {
      summary: '발주서입니다.',
      // 실제로 나왔던 값입니다. 문서 내용이 아니라 파일 메타데이터입니다.
      extracted_fields: { media_type: 'application/pdf', other_numeric_value: 87 },
    },
    null,
  )
  assert.deepEqual(Object.keys(model).sort(), ['keyPoints', 'lead', 'riskFlags', 'salesRelevance'])
})

test('payload 가 없으면 마크다운을 읽는다', () => {
  const model = toSummaryModel(null, MARKDOWN)
  assert.match(model.lead, /^포커스바이오솔루션/)
  assert.equal(model.keyPoints.length, 2)
  assert.deepEqual(model.salesRelevance, ['프로브 재구매 수요가 확인됩니다.'])
})

test("'없음' 은 값이 아니라 빈 칸이라 목록에서 뺀다", () => {
  assert.deepEqual(toSummaryModel(null, MARKDOWN).riskFlags, [])
  assert.deepEqual(toSummaryModel({ summary: 'x', risk_flags: ['없음', '-'] }, null).riskFlags, [])
})

test('구버전 요약의 제목·추출 필드·출처 구간을 버린다', () => {
  const model = parseSummaryMarkdown(
    [
      '# 문서 요약',
      '',
      '도입 문단입니다.',
      '',
      '## 추출 필드',
      '',
      '- 총액: 100',
      '',
      '## 출처',
      '',
      '- p.1',
      '',
      '## 주요 내용',
      '',
      '- 살아남는 항목',
    ].join('\n'),
  )
  assert.equal(model.lead, '도입 문단입니다.')
  assert.deepEqual(model.keyPoints, ['살아남는 항목'])
})

test('모양이 어긋난 payload 에서 던지지 않고 읽을 수 있는 것만 남긴다', () => {
  const model = toSummaryModel(
    {
      summary: { 잘못된: '모양' },
      key_points: ['정상 항목', 42, null, { a: 1 }, '  '],
      sales_relevance: '배열이 아님',
      risk_flags: null,
    },
    MARKDOWN,
  )
  assert.deepEqual(model.keyPoints, ['정상 항목', '42'])
  assert.deepEqual(model.salesRelevance, [])
  // summary 를 읽지 못했으므로 도입 문단은 마크다운에서 가져옵니다.
  assert.match(model.lead, /^포커스바이오솔루션/)
})

test('payload 가 통째로 비면 마크다운으로 물러선다', () => {
  const model = toSummaryModel({ summary: '', key_points: [] }, MARKDOWN)
  assert.equal(model.keyPoints.length, 2)
})

test('그릴 것이 없으면 빈 요약으로 알린다', () => {
  assert.equal(isEmptySummary(toSummaryModel(null, '')), true)
  assert.equal(isEmptySummary(toSummaryModel(null, MARKDOWN)), false)
})
