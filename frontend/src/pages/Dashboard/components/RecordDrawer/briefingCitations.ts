/*
 * 브리핑 본문에서 "이 문장은 문서에서 왔다"는 자리를 찾습니다.
 *
 * 브리핑은 원문을 그대로 옮기지 않고 다시 씁니다. 그래서 인용한 문장을 글자로는 찾을 수
 * 없고, 문장과 원문 구절이 함께 쓰는 낱말로 가늠합니다. 무게를 매기는 기준(숫자 > 업무
 * 낱말 > 그 밖의 말)은 백엔드가 카드에 문서를 이어 붙일 때 쓰는 _document_match_score 와
 * 같습니다 — 두 곳이 서로 다른 근거를 고르면 문단 앞 링크와 형광펜이 어긋납니다.
 *
 * 한 가지만 다릅니다. 여기서는 낱말의 앞 두 글자만 봅니다(아래 stem). 백엔드는 문서 여럿
 * 중 하나를 고르는 자리라 조사가 붙은 채로도 순위가 갈리지만, 여기서는 문단 안의 문장
 * 하나를 짚어야 해서 '대금'과 '대금을'이 겹치지 않으면 인용을 거의 못 찾습니다.
 *
 * React 를 쓰지 않으므로 그대로 테스트합니다(tests/briefingCitations.test.mjs).
 */
import { sentenceEnds } from './briefingReveal'

/**
 * 낱말 하나를 견줄 수 있는 모양으로 줄입니다.
 *
 * 한글은 같은 말이라도 조사·어미가 달라붙어('대금'과 '대금을', '지급'과 '지급합니다')
 * 글자 그대로는 겹치지 않습니다. 업무에 쓰는 말의 뿌리는 대개 두 글자라 앞 두 글자만
 * 봅니다. 영문과 숫자는 통째로 둡니다 — 두 글자로 자르면 서로 다른 말이 죄다 붙습니다.
 */
function stem(token: string): string {
  return /^[가-힣]/.test(token) ? token.slice(0, 2) : token
}

/** 어디에나 붙어 근거가 되지 못하는 말. 백엔드 _MATCH_STOP_WORDS 와 같습니다. */
const STOP_WORDS = new Set(['확인', '필요', '이번', '최종', '관련', '조건', '정보', '자료'])

/**
 * 겹치면 같은 내용을 가리킬 만한 업무 낱말. 백엔드 _DOCUMENT_MATCH_TERMS 와 같은 목록을,
 * 견줄 낱말과 같은 모양으로 줄여 둡니다.
 */
const TERMS = new Set(
  [
    '부가세',
    'vat',
    '설치',
    '납기',
    '지급',
    '지급조건',
    '금액',
    '견적',
    '계약',
    '발주',
    '유효기간',
    '할인',
  ].map(stem),
)

/**
 * 문장 하나를 원문 구절에 잇기 위한 최소 점수.
 *
 * 숫자 하나(4점)나 업무 낱말 둘(4점)처럼 "우연히 겹쳤다"고 보기 어려운 만큼은 겹쳐야
 * 형광펜을 긋습니다. 엉뚱한 문장을 인용으로 칠하는 쪽이 강조가 빠지는 쪽보다 나쁩니다.
 */
const MIN_SCORE = 4

export interface TextRange {
  start: number
  end: number
}

/** 어느 자료에서 온 문장인지까지 붙은 자리. 문장 끝의 원문 링크가 이 값을 씁니다. */
export interface CitedRange extends TextRange {
  /** 이 문장을 짚은 근거(BriefingReference.key). */
  key: string
  /** 문장이 끝까지 드러났는지. 타자 치는 중에는 false 라, 그동안은 링크를 달지 않습니다. */
  done: boolean
}

/** 본문에서 찾아볼 원문 구절 하나. */
export interface CitationSource {
  key: string
  excerpts: string[]
}

/** 견줄 낱말만 남깁니다. 자른 뒤에 걸러야 '확인하세요' 같은 말도 함께 빠집니다. */
export function matchTokens(value: string): Set<string> {
  const tokens = value.toLowerCase().match(/[가-힣a-z]{2,}|\d[\d,.-]*/g) ?? []
  return new Set(tokens.map(stem).filter((token) => !STOP_WORDS.has(token)))
}

/** 숫자·업무 낱말을 일반 낱말보다 무겁게 셉니다. */
function overlapScore(sentence: Set<string>, excerpt: Set<string>): number {
  let score = 0
  sentence.forEach((token) => {
    if (!excerpt.has(token)) return
    score += /^\d/.test(token) ? 4 : TERMS.has(token) ? 2 : 1
  })
  return score
}

/**
 * 본문을 문장 단위로 끊어 각 문장이 차지한 자리를 돌려줍니다.
 *
 * 끊는 자리는 타자 치며 쉬는 자리와 같습니다(briefingReveal.sentenceEnds). 형광펜이
 * 쉬는 자리와 다른 곳에서 끊기면 같은 글이 두 규칙으로 나뉘어 읽힙니다. 앞뒤 공백은
 * 빼서 형광펜이 문장 밖으로 번지지 않게 합니다.
 */
export function sentenceRanges(text: string): TextRange[] {
  const bounds = [0, ...sentenceEnds(text), text.length]
  const ranges: TextRange[] = []
  for (let index = 0; index < bounds.length - 1; index += 1) {
    let start = bounds[index]
    let end = bounds[index + 1]
    while (start < end && /\s/.test(text[start])) start += 1
    while (end > start && /\s/.test(text[end - 1])) end -= 1
    if (end > start) ranges.push({ start, end })
  }
  return ranges
}

/**
 * 자료마다 가장 많이 겹치는 문장 하나를 고릅니다.
 *
 * 자료 하나가 문장 하나를 고르므로, 인용이 두 건이어도 문단이 통째로 칠해지지 않습니다.
 * 겹치는 낱말이 모자라면 아무 문장도 고르지 않습니다 — 그때는 문단 끝에 파일 이름 링크가
 * 대신 섭니다. 엉뚱한 문장을 칠하고 거기에 원문 링크까지 거는 쪽이 훨씬 나쁩니다.
 *
 * 한 문장을 두 자료가 골랐으면 먼저 고른 자료가 가집니다. 한 자리에 링크를 둘 달면 어느
 * 것이 이 문장의 근거인지 읽히지 않습니다.
 */
export function citedRanges(body: string, sources: CitationSource[]): CitedRange[] {
  if (!body) return []
  const sentences = sentenceRanges(body).map((range) => ({
    range,
    tokens: matchTokens(body.slice(range.start, range.end)),
  }))
  const picked: CitedRange[] = []
  for (const source of sources) {
    let bestScore = MIN_SCORE - 1
    let best: TextRange | null = null
    for (const excerpt of source.excerpts) {
      const tokens = matchTokens(excerpt)
      if (tokens.size === 0) continue
      for (const sentence of sentences) {
        if (picked.some((range) => range.start === sentence.range.start)) continue
        const score = overlapScore(sentence.tokens, tokens)
        if (score > bestScore) {
          bestScore = score
          best = sentence.range
        }
      }
    }
    if (best) picked.push({ ...best, key: source.key, done: true })
  }
  return picked.sort((left, right) => left.start - right.start)
}

/**
 * 아직 다 치지 않은 글에 맞춰 자리를 잘라 냅니다. 자리는 다 쓴 본문에서 재고, 그리기
 * 직전에만 줄입니다 — 치는 도중의 토막으로 재면 문장이 늘어날 때마다 고른 문장이 바뀝니다.
 *
 * 잘린 문장은 `done` 이 false 가 됩니다. 문장 끝의 원문 링크는 그동안 달리지 않습니다 —
 * 아직 쳐지는 중인 글을 따라 아이콘이 오른쪽으로 끌려다니면 읽는 눈이 그걸 쫓습니다.
 */
export function clipRanges(ranges: CitedRange[], length: number): CitedRange[] {
  return ranges
    .filter((range) => range.start < length)
    .map((range) => ({
      ...range,
      end: Math.min(range.end, length),
      done: range.end <= length,
    }))
}
