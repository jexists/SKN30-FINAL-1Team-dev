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
  '요청 대상',
]

// 필드 사이 구분자는 '·' 와 '|' 둘 다 관측됩니다. 앞뒤 공백을 요구해야
// '내일·기준일 미확인' 처럼 값 안에 붙어 있는 가운뎃점을 자르지 않습니다.
const SEPARATOR = /\s+[·|]\s+/

/*
 * 일일·주간·월간의 마지막 구획은 '할 일 — 담당 미지정, 기한 미확인, 완료 기준: …' 꼴로 옵니다.
 * 지침이 구분자를 정해 주지 않아 딜 보고서(' · ')와 다른 꼴이 나옵니다.
 *
 * 꼬리에 알려진 이름표가 있을 때만 자릅니다. 그냥 줄표·쉼표로 자르면
 * '설치 조건, 기존 장비와의 역할 분담, … 확인 — 담당 미지정' 같은 줄의 할 일이 조각납니다.
 */
// 줄표 뒤 첫 조각이 이름표가 아닌 때가 있습니다 — '… — 합의된 후속 조치, 담당 미지정, …'
// 처럼 상태가 이름표 없이 먼저 옵니다. 꼬리 어딘가에 이름표가 있으면 자릅니다.
const TAIL = new RegExp(`\\s+[—–]\\s+(?=[^\\n]*?(?:${FIELD_LABELS.join('|')})[\\s:])`)
const TAIL_SEPARATOR = new RegExp(`\\s*[,·|]\\s*(?=(?:${FIELD_LABELS.join('|')})[\\s:])`)

const HEADING = /^\*\*(.+?)\*\*$/
// 콜론 없이 '담당 미지정' 처럼도 옵니다. 알려진 빈 값 낱말만 허용해
// '담당 배정 요청' 같은 평범한 할 일이 이름표로 오인되지 않게 합니다.
const FIELD = new RegExp(`^(${FIELD_LABELS.join('|')})\\s*(?::\\s*(.+)|\\s+(미지정|미확인|미정))$`)

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

/**
 * 목록 한 줄을 할 일과 이름표로 가릅니다.
 * 이름표가 하나도 없으면 줄 전체가 할 일이 됩니다 — 버리지 않습니다.
 */
function actionOf(item: string): ReportAction {
  // 줄표 꼬리가 있으면 앞은 통째로 할 일입니다. 꼬리만 이름표로 가릅니다.
  const at = item.search(TAIL)
  const head = at < 0 ? '' : item.slice(0, at)
  const parts =
    at < 0 ? item.split(SEPARATOR) : item.slice(at).replace(TAIL, '').split(TAIL_SEPARATOR)
  const fields: ReportField[] = []
  const task: string[] = head ? [strong(head).trim()] : []
  for (const part of parts) {
    const matched = FIELD.exec(part.trim())
    if (matched) fields.push({ label: matched[1], value: strong(matched[2] ?? matched[3]).trim() })
    // 꼬리에서 이름표가 없는 조각은 상태입니다. 할 일은 이미 줄표 앞에 다 있습니다.
    else if (head) fields.push({ label: '상태', value: strong(part).trim() })
    else task.push(strong(part).trim())
  }
  return { task: task.filter(Boolean).join(' · '), fields }
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
  return actions.some((action) => action.fields.length) ? actions : undefined
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
