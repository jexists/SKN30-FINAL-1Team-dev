/*
 * 보고서 본문을 구획으로 읽습니다.
 *
 * 서버는 본문을 정해진 꼴로 씁니다(backend/app/agents/reports/skills/report-style/SKILL.md):
 * 고정 항목마다 굵은 소제목을 독립된 한 줄에 쓰고, 빈 줄 뒤에 서술 문단을 둡니다. 마지막
 * 항목만 목록이고, 그 목록은 할 일 · 담당 · 기한 · 완료 기준을 밝힙니다. 미팅 딜별·일일·주간·
 * 월간이 모두 같은 꼴이라 항목 이름은 보지 않고 꼴만 봅니다.
 *
 * 미팅 공통·미지정 기록은 소제목 없이 평평한 목록입니다. 그런 본문은 null 로 돌려보내
 * 부르는 쪽이 원문 그대로 그리게 합니다.
 */

/*
 * 후속 조치 한 줄에 붙는 이름표. 서버가 쓰는 것만 받습니다.
 * '담당자' 는 반드시 '담당' 앞에 둡니다 — 정규식 교대는 앞에서부터 맞추므로
 * 짧은 쪽이 먼저 서면 '담당자: 본인' 이 '담당' 에 걸렸다가 통째로 실패합니다.
 */
const FIELD_LABELS = [
  '담당자',
  '담당',
  '기한',
  '완료 기준',
  '상태',
  '이행 여부',
  '조건',
  '선행조건',
  '전달 방식',
  '요청 대상',
]

/*
 * 한 줄을 구분자로 가르지 않습니다. 보고서마다 구분자가 다릅니다 — ' · ', ' | ', ' — ',
 * 쉼표, 쌍반점, 마침표가 모두 관측됐습니다. 구분자를 쫓으면 새 꼴이 올 때마다 깨집니다.
 * 대신 이름표는 지침이 정해 둔 닫힌 목록이므로, 이름표가 선 자리를 찾아 그 사이를 값으로
 * 읽습니다. 그러면 구분자가 무엇이든 같은 결과가 나옵니다.
 */

// 줄 맨 앞에서 할 일을 여는 이름표. 칸이 아니라 제목이 됩니다.
const TASK_LABEL = '할 일'
const ANCHOR_LABELS = [TASK_LABEL, ...FIELD_LABELS].join('|')
// '담당자·기한 미확인' 처럼 이름표 여럿이 한 값을 나눠 쓰기도 합니다.
const COMPOUND = `(?:${ANCHOR_LABELS})(?:·(?:${ANCHOR_LABELS}))*`
const KNOWN_ONLY = new RegExp(`^${COMPOUND}$`)
// 콜론 없이 '담당 미지정' 처럼도 옵니다. 알려진 빈 값 낱말만 허용해
// '담당 배정 요청' 같은 평범한 할 일이 이름표로 오인되지 않게 합니다.
const BLANK_WORDS = '미지정|미확인|미정'
// 지침에 없는 이름표도 옵니다('요청·진행 주체:'). 짧은 한 토막만 이름표로 봅니다.
const OTHER_LABEL = '[^\\s:：.,;|—–][^:：.,;|—–]{0,14}'

/*
 * 이름표가 선 자리. 셋 중 하나입니다.
 *   1. 아는 이름표 + 쌍점        '담당자: 본인'
 *   2. 아는 이름표 + 빈 값 낱말   '담당 미지정'
 *   3. 모르는 이름표 + 쌍점      '요청·진행 주체: 고객이 …' (문장 경계 뒤에서만)
 */
const ANCHOR = new RegExp(
  `(?:^|\\s)(${COMPOUND})\\s*[::]` +
    `|(?:^|\\s)(${COMPOUND})\\s+(${BLANK_WORDS})(?=$|[\\s.,;·|])` +
    `|(?:^|[.,;]\\s|\\s[—–]\\s|\\s[·|]\\s)(${OTHER_LABEL})\\s*[::]`,
  'g',
)

/*
 * 지시문이 정한 칸 순서(할 일 · 담당자 · 기한 · 완료 기준). 이름표 없이 온 조각을
 * 이 순서의 다음 빈칸으로 읽습니다 — 이름표를 지어내는 게 아니라 지시문의 순서를 씁니다.
 */
const FIELD_ORDER = ['담당자', '기한', '완료 기준']

/*
 * 서버가 쓰는 상태 낱말. 이름표 없이 온 조각을 상태로 올릴지 여기서만 정합니다 —
 * 아무 조각이나 상태로 만들면 '담당자' 같은 말이 상태 배지로 올라갑니다.
 * 긴 쪽을 앞에 둡니다 — 정규식 교대는 앞에서부터 맞습니다.
 */
const STATUS_WORDS = '합의된 후속 조치|승인 대기|승인 완료|검토 필요|합의|요청|제안|필요'

// 할 일 제목에 상태가 접두사로 붙어 오는 꼴. ' · 상태: 합의' 와 같은 정보라 필드로 옮깁니다.
const STATUS_PREFIX = new RegExp(`^(${STATUS_WORDS})\\s*[::]\\s*`)

/*
 * 이름표 없는 조각이 통째로 상태일 때. '요청·수락 여부 미확인' 처럼 뒤가 붙어 와도 받습니다.
 * 쌍점이 있으면 상태가 아니라 제 이름표를 단 칸입니다.
 */
const STATUS_VALUE = new RegExp(`^(?:${STATUS_WORDS})(?:[·, ][^::]*)?$`)

const HEADING = /^\*\*(.+?)\*\*$/

/*
 * 이름표가 하나도 없는 줄의 꼬리. '견적 수신 여부 확인 — 다음 주 목요일 오후; …' 처럼
 * 옵니다. 어느 칸인지 알 수 없으므로 칸 이름을 지어내지 않고 통째로 비고로 답니다.
 * 같은 구획의 다른 줄에 이름표가 있을 때만 씁니다 — 논의 목록이 카드로 부풀지 않게.
 *
 * 쌍점 앞이 이름표나 상태 낱말이면 칸 안의 쌍점이므로 자르지 않습니다.
 */
const LOOSE_TAIL = new RegExp(`\\s+[—–]\\s+|(?<!${ANCHOR_LABELS}|${STATUS_WORDS}):\\s+`)
const NOTE = '비고'

// 할 일 앞뒤에 남는 구분자 부스러기. 값 끝의 마침표·쉼표도 같이 떨어냅니다.
const TRIM = /^[\s.,;:：·|—–]+|[\s.,;:：·|—–]+$/g
const DASH = /\s+[—–]\s+/

export interface ReportField {
  label: string
  value: string
}

export interface ReportAction {
  /** 할 일. 이름표가 붙지 않은 앞머리입니다. */
  task: string
  fields: ReportField[]
}

export interface ReportSection {
  /** 소제목. 첫 소제목 앞에 있던 글은 이름 없는 구획이 됩니다. */
  heading: string
  /** 구획 본문 Markdown. 그대로 ReportBody 에 넘길 수 있습니다. */
  body: string
  /** 목록이면서 이름표가 하나라도 붙은 구획만 채워집니다. */
  actions?: ReportAction[]
}

function strong(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, '$1')
}

/** 이름표 없이 온 꼬리 조각을 정해진 칸 순서의 다음 빈칸에 넣습니다. */
function fill(fields: ReportField[], value: string): void {
  if (!value) return
  // 맨 앞 조각이 상태 낱말이면 상태입니다 — '… — 합의된 후속 조치, 담당 미지정, …'
  // 상태 낱말이 아니면 상태로 만들지 않습니다. '담당자' 가 상태 배지로 올라가던 자리입니다.
  if (!fields.length && STATUS_VALUE.test(value)) {
    fields.push({ label: '상태', value })
    return
  }
  const used = new Set(fields.map((field) => (field.label === '담당' ? '담당자' : field.label)))
  const free = FIELD_ORDER.filter((label) => !used.has(label))
  // 칸이 다 찼으면 앞 값이 잘린 것입니다. 버리지 않고 이어 붙입니다.
  if (!free.length) {
    fields[fields.length - 1].value += `, ${value}`
    return
  }
  /*
   * '담당 미지정, 다음 주 목요일 오후, 견적 수신 확인만 …' 처럼 이름표가 도중에 끊기고
   * 남은 값이 쉼표로 이어집니다. 빈칸이 둘 이상 남았을 때만 첫 쉼표에서 한 번 가릅니다 —
   * 마지막 빈칸에 들어갈 값은 통째로 두어야 줄글 안의 쉼표가 조각나지 않습니다.
   */
  const at = free.length > 1 ? value.indexOf(', ') : -1
  fields.push({ label: free[0], value: at < 0 ? value : value.slice(0, at) })
  if (at >= 0) fill(fields, value.slice(at + 2).trim())
}

/** 구분자 부스러기와 굵은 표시를 떼어 낸 알맹이. */
function clean(text: string): string {
  return strong(text).replace(TRIM, '')
}

interface Anchor {
  start: number
  valueStart: number
  label: string
  /** 빈 값 낱말로 온 칸. 값이 이 낱말 하나로 끝나고 뒤는 다른 조각입니다. */
  blank?: string
  known: boolean
}

/**
 * 한 줄에서 이름표가 선 자리를 모두 찾습니다.
 * 아는 이름표가 하나도 없으면 이 줄은 카드가 아닙니다 — 빈 목록을 돌려줍니다.
 */
function anchorsOf(item: string): Anchor[] {
  const found: Anchor[] = []
  for (const match of item.matchAll(ANCHOR)) {
    const label = (match[1] ?? match[2] ?? match[4]).trim()
    found.push({
      start: match.index,
      valueStart: match.index + match[0].length,
      label,
      blank: match[3],
      known: KNOWN_ONLY.test(label),
    })
  }
  // 상태 낱말은 이름표가 아니라 제목에 붙은 접두사입니다 — STATUS_PREFIX 가 칸으로 옮깁니다.
  const anchors = found.filter(
    (anchor) => anchor.known || anchor.start > 0 || !STATUS_VALUE.test(anchor.label),
  )
  found.length = 0
  found.push(...anchors)
  if (!found.some((anchor) => anchor.known)) return []

  // '담당: 담당 미지정' 처럼 값이 그대로 이름표 꼴이면 뒤엣것은 칸이 아니라 값입니다.
  return found.filter((anchor, index) => {
    const previous = found[index - 1]
    if (!anchor.blank || !previous?.known || previous.blank) return true
    return item.slice(previous.valueStart, anchor.start).trim() !== ''
  })
}

/**
 * 목록 한 줄을 할 일과 이름표로 가릅니다.
 * 이름표가 하나도 없으면 줄 전체가 할 일이 됩니다 — 버리지 않습니다.
 */
function actionOf(item: string): ReportAction {
  const anchors = anchorsOf(item)
  if (!anchors.length) return { task: clean(item), fields: [] }

  const fields: ReportField[] = []
  // 아는 이름표만 가운뎃점으로 폅니다. '요청·진행 주체' 는 통째로 한 이름표입니다.
  const push = (anchor: Anchor, value: string) => {
    const labels = anchor.known ? anchor.label.split('·') : [anchor.label]
    for (const label of labels) fields.push({ label, value })
  }

  // 첫 이름표 앞은 할 일입니다. 파이프 꼴은 가운뎃점으로 맞춰 둡니다.
  let title = clean(item.slice(0, anchors[0].start)).replace(/\s+\|\s+/g, ' · ')
  // '할 일 — 합의된 후속 조치, 담당 미지정' 처럼 할 일과 첫 칸 사이에 이름표 없는 조각이 옵니다.
  const dash = title.search(DASH)
  if (dash > 0) {
    const lead = title.slice(dash).replace(DASH, '')
    title = title.slice(0, dash)
    if (STATUS_VALUE.test(lead)) fields.push({ label: '상태', value: lead })
    // 값을 잃은 이름표 한 조각은 버립니다. 그 밖의 말은 할 일에 되돌립니다.
    else if (!KNOWN_ONLY.test(lead)) title = `${title} · ${lead}`
  }

  for (const [index, anchor] of anchors.entries()) {
    const end = anchors[index + 1]?.start ?? item.length
    const rest = clean(item.slice(anchor.valueStart, end))
    // 줄 맨 앞의 '할 일:' 과 모르는 이름표는 칸이 아니라 제목입니다.
    if (!title && anchor.start === 0 && (anchor.label === TASK_LABEL || !anchor.known)) {
      if (anchor.label === TASK_LABEL) title = rest
      else {
        title = anchor.label
        if (rest) fields.push({ label: NOTE, value: rest })
      }
      continue
    }
    // 줄표는 값 안에 오지 않습니다. 값 뒤에 줄표가 붙으면 그 뒤는 이름표를 빠뜨린 다음 칸입니다.
    const cut = rest.search(DASH)
    const value = cut < 0 ? rest : rest.slice(0, cut)
    const spill = cut < 0 ? '' : clean(rest.slice(cut))

    if (anchor.label === TASK_LABEL) fill(fields, value)
    else if (anchor.blank) push(anchor, anchor.blank)
    else push(anchor, value)
    // 빈 값 낱말 뒤에 이어진 조각과 줄표 뒤의 조각은 이름표가 빠진 남은 칸입니다.
    if (anchor.blank && value) fill(fields, value)
    if (spill) fill(fields, spill)
  }

  const status = STATUS_PREFIX.exec(title)
  if (status && !fields.some((field) => field.label === '상태')) {
    title = title.slice(status[0].length)
    fields.unshift({ label: '상태', value: status[1] })
  }
  return { task: title, fields }
}

/** 구획 본문이 목록뿐이고 이름표가 하나라도 있으면 후속 조치로 읽습니다. */
function actionsOf(body: string): ReportAction[] | undefined {
  const lines = body.split('\n').filter((line) => line.trim() !== '')
  if (!lines.length || !lines.every((line) => /^\s*[-*]\s+/.test(line))) return undefined
  const actions = lines
    .map((line) => actionOf(line.replace(/^\s*[-*]\s+/, '').trim()))
    .reduce<ReportAction[]>((list, action) => {
      // 한 조치의 이름표가 줄마다 따로 오는 경우가 있습니다. 할 일 없이 이름표만
      // 남은 줄은 앞 조치에 붙입니다 — 조치 하나가 상자 네댓 개로 쪼개지지 않게.
      const previous = list[list.length - 1]
      if (!action.task && previous) previous.fields.push(...action.fields)
      else list.push(action)
      return list
    }, [])
  if (!actions.some((action) => action.fields.length)) return undefined
  for (const action of actions) {
    if (action.fields.length) continue
    const at = action.task.search(LOOSE_TAIL)
    if (at <= 0) continue
    const note = action.task.slice(at).replace(LOOSE_TAIL, '').trim()
    if (!note) continue
    action.fields.push({ label: NOTE, value: note })
    action.task = action.task.slice(0, at)
  }
  return actions
}

/**
 * 본문을 구획 목록으로 읽습니다. 소제목이 하나도 없으면 null 입니다.
 *
 * 스트리밍 중에는 본문이 잘린 채 들어옵니다. 순수 문자열 처리라 부분 입력에서도 깨지지 않고,
 * 구획이 도착하는 대로 하나씩 늘어납니다.
 */
export function reportSections(body: string): ReportSection[] | null {
  if (!body.trim()) return null
  const sections: ReportSection[] = []
  let heading = ''
  let lines: string[] = []

  const close = () => {
    const text = lines.join('\n').trim()
    // 소제목만 오고 내용이 아직 안 온 구획도 남깁니다 — 스트리밍 중 자리를 잡아 둡니다.
    if (heading || text) sections.push({ heading, body: text, actions: actionsOf(text) })
    lines = []
  }

  for (const line of body.split('\n')) {
    const matched = HEADING.exec(line.trim())
    if (!matched) {
      lines.push(line)
      continue
    }
    close()
    heading = matched[1].trim()
  }
  close()

  // 소제목이 없으면 우리가 아는 꼴이 아닙니다. 손대지 않고 원문을 돌려주게 합니다.
  return sections.some((section) => section.heading) ? sections : null
}
