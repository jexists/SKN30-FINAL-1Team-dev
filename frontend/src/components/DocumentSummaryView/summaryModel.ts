/**
 * 자료요약 Agent 의 결과를 화면이 그릴 수 있는 모양으로 정규화합니다.
 *
 * 서버는 같은 요약을 두 가지로 내려 줍니다. 구조화 JSON(`summary_payload`)과, 그것을
 * 헤딩·불릿으로 납작하게 편 마크다운(`summary_markdown`)입니다. 자료실은 둘 다 받고,
 * 대시보드의 관련 자료 목록은 마크다운만 받습니다. 화면마다 다른 코드를 두지 않도록
 * 여기서 둘을 같은 모델로 맞춥니다 — JSON 이 있으면 그쪽을, 없으면 마크다운을 읽습니다.
 *
 * 들어오는 값은 LLM 이 만든 것이라 형식을 보장할 수 없습니다. 타입 단언으로 넘기지 않고
 * 값마다 모양을 확인해서 거릅니다. 읽지 못한 항목은 버리되, 나머지는 살려서 그립니다.
 *
 * `extracted_fields` 는 읽지 않습니다. 키가 자유형이라 실제로는 'media type:
 * application/pdf', 'other numeric value: 87' 처럼 문서 내용이 아닌 값이 섞여 나옵니다.
 * 화면에 세울 만한 값이 되려면 백엔드가 먼저 고정 스키마를 가져야 합니다.
 */

export interface DocumentSummaryModel {
  /** 도입 문단. */
  lead: string
  keyPoints: string[]
  salesRelevance: string[]
  riskFlags: string[]
}

/**
 * 값이 없을 때 서버가 찍는 자리 채우기입니다. 이것들은 내용이 아니라 빈 칸이라서,
 * 목록에 남기면 "리스크: 없음" 같은 줄이 실제 리스크와 같은 자리를 차지합니다.
 */
const PLACEHOLDERS = new Set(['없음', '해당 없음', '해당없음', '-', '–', '—', 'N/A', 'n/a'])

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** 글로 쓸 수 있는 값만 남깁니다. 나머지는 null 로 걸러 냅니다. */
function scalarText(value: unknown): string | null {
  if (typeof value === 'string') return value.trim() || null
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : null
  if (typeof value === 'boolean') return value ? '예' : '아니오'
  return null
}

function isPlaceholder(text: string): boolean {
  return PLACEHOLDERS.has(text)
}

/**
 * 문자열 목록을 받습니다. 배열이 아니거나 원소가 글이 아니면 그 원소만 버립니다.
 * 하나가 깨졌다고 목록 전체를 버리면 읽을 수 있는 항목까지 화면에서 사라집니다.
 */
function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const result: string[] = []
  for (const item of value) {
    const text = scalarText(item)
    if (text !== null && !isPlaceholder(text)) result.push(text)
  }
  return result
}

/** 마크다운 소제목을 모델의 어느 칸에 넣을지 가릅니다. */
type Bucket = 'lead' | 'keyPoints' | 'salesRelevance' | 'riskFlags' | 'drop'

const BUCKETS: Record<string, Bucket> = {
  '문서 요약': 'lead',
  문서요약: 'lead',
  '핵심 요약': 'lead',
  요약: 'lead',
  '주요 내용': 'keyPoints',
  '영업 참고사항': 'salesRelevance',
  리스크: 'riskFlags',
  // 추출 필드와 출처는 구버전 요약에만 본문으로 들어 있습니다. 둘 다 화면에 세우지
  // 않으므로, 본문에서 만나면 그 구간을 통째로 버립니다.
  '추출 필드': 'drop',
  출처: 'drop',
}

/**
 * 서버가 만든 요약 마크다운을 되읽습니다.
 *
 * 형식은 `_summary_markdown()` 이 고정으로 찍는 `## 소제목` + `- 항목` 뿐입니다. 그래서
 * 마크다운 파서를 부르지 않고 줄 단위로 읽습니다 — 여기서 필요한 것은 문단 구조가 아니라
 * 어느 소제목 아래의 항목인가뿐입니다.
 */
export function parseSummaryMarkdown(markdown: string): DocumentSummaryModel {
  const model: DocumentSummaryModel = {
    lead: '',
    keyPoints: [],
    salesRelevance: [],
    riskFlags: [],
  }
  const leadLines: string[] = []
  const lists: Record<Exclude<Bucket, 'lead' | 'drop'>, string[]> = {
    keyPoints: model.keyPoints,
    salesRelevance: model.salesRelevance,
    riskFlags: model.riskFlags,
  }
  // 소제목이 서기 전의 글은 도입 문단으로 봅니다.
  let bucket: Bucket = 'lead'

  for (const raw of markdown.split('\n')) {
    const line = raw.trim()
    if (!line) continue

    const heading = /^#{1,6}\s+(.+)$/.exec(line)
    if (heading) {
      // 모르는 소제목은 버리지 않고 도입 문단으로 받습니다. 서버가 항목을 늘렸을 때
      // 그 내용이 화면에서 통째로 사라지는 편보다 낫습니다.
      bucket = BUCKETS[heading[1].trim()] ?? 'lead'
      continue
    }
    if (bucket === 'drop') continue

    const bullet = /^[-*+]\s+(.+)$/.exec(line)
    const text = bullet ? bullet[1].trim() : line
    if (!text || isPlaceholder(text)) continue

    if (bucket === 'lead') leadLines.push(text)
    else lists[bucket].push(text)
  }

  model.lead = leadLines.join('\n')
  return model
}

/**
 * 구조화 JSON 을 우선 읽고, 없으면 마크다운으로 물러섭니다.
 *
 * `payload` 는 서버에서 온 검증되지 않은 JSON 입니다. 모양을 확인한 뒤에만 씁니다.
 */
export function toSummaryModel(payload: unknown, markdown: string | null): DocumentSummaryModel {
  const fromMarkdown = parseSummaryMarkdown(markdown ?? '')
  if (!isPlainObject(payload)) return fromMarkdown

  const lead = scalarText(payload.summary) ?? ''
  const keyPoints = stringList(payload.key_points)
  const salesRelevance = stringList(payload.sales_relevance)
  const riskFlags = stringList(payload.risk_flags)

  // 글 항목이 하나도 읽히지 않았다면 payload 쪽이 비었거나 모양이 다른 것입니다.
  // 그때는 마크다운으로 본문을 채웁니다.
  if (!lead && !keyPoints.length && !salesRelevance.length && !riskFlags.length) {
    return fromMarkdown
  }
  return { lead: lead || fromMarkdown.lead, keyPoints, salesRelevance, riskFlags }
}

/** 그릴 것이 하나라도 있는지. 없으면 화면에서 섹션째 비웁니다. */
export function isEmptySummary(model: DocumentSummaryModel): boolean {
  return (
    !model.lead &&
    model.keyPoints.length === 0 &&
    model.salesRelevance.length === 0 &&
    model.riskFlags.length === 0
  )
}
