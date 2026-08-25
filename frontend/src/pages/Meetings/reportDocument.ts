/**
 * 보고서 한 편(문서) 과 항목별 값(values) 사이를 오갑니다.
 *
 * 저장되는 모양은 지금까지와 같은 `content.values` 입니다. 백엔드도 업무보고도 그
 * 모양을 그대로 읽습니다. 문서는 화면에서 고쳐 쓰기 좋으라고 잠깐 만드는 형태이고,
 * 저장 직전에 다시 항목으로 돌아갑니다.
 *
 *   values ──toDocument──▶ markdown ──toHtml──▶ TinyMCE
 *   values ◀──toValues─── markdown ◀─toMarkdown─ TinyMCE
 *
 * 항목을 가르는 것은 `## 라벨` 한 줄뿐입니다. 그래서 이 제목은 화면에서 지울 수 없게
 * 막고(mceNonEditable), 저장 직전에 한 번 더 세어 봅니다. 제목이 사라지면 그 아래
 * 글이 어느 항목인지 알 방법이 없기 때문입니다.
 */
import { marked } from 'marked'
import TurndownService from 'turndown'

import type { ReportTemplate } from '@/types'

/** TinyMCE 가 이 클래스를 보고 그 블록을 편집 대상에서 뺍니다. */
export const LOCKED_CLASS = 'mceNonEditable'

const turndown = new TurndownService({
  headingStyle: 'atx',
  bulletListMarker: '-',
  emDelimiter: '_',
})

/*
 * 기본 규칙은 '-' 뒤에 공백 세 칸을 넣습니다. 이 값을 그대로 읽어 요약으로 쓰는
 * 곳(업무보고 목록·활동 선택)이 있어서, 사람이 볼 때 어색하지 않게 한 칸으로 줄입니다.
 */
turndown.addRule('tightListItem', {
  filter: 'li',
  replacement: (content, node) => {
    const body = content.trim().replace(/\n/g, '\n  ')
    const parent = node.parentNode as HTMLElement
    const marker =
      parent.nodeName === 'OL'
        ? `${Array.prototype.indexOf.call(parent.children, node) + 1}. `
        : '- '
    return `${marker}${body}${node.nextSibling ? '\n' : ''}`
  },
})

const heading = (label: string) => `## ${label}`

/** 항목별 값을 '## 라벨' 로 이어 붙여 문서 한 편으로 만듭니다. */
export function toDocument(template: ReportTemplate, values: Record<string, string>): string {
  return template.fields
    .map((field) => `${heading(field.label)}\n\n${(values[field.id] ?? '').trim()}`)
    .join('\n\n')
    .trim()
}

/** 자유롭게 쓴 글이 갈 곳. 제목 없이 쓴 문서는 통째로 여기 담깁니다. */
function catchAllId(template: ReportTemplate): string {
  return template.fields[template.fields.length - 1]?.id ?? ''
}

const render = (body: string) => (body.trim() ? marked.parse(body, { async: false }) : '<p></p>')

export interface DocumentHtml {
  html: string
  /** 이 문서에 실제로 그린 항목 제목의 id. 저장 직전 검사의 기준이 됩니다. */
  sections: string[]
}

/**
 * 문서를 TinyMCE 가 받는 HTML 로 바꿉니다.
 *
 * 세 갈래입니다.
 *
 *   아무것도 없음        빈 문단 하나. 백지입니다.
 *   자유로 쓴 글만 있음   제목 없이 글만. 백지에 쓴 것이 그대로 돌아옵니다.
 *   그 밖                양식 그대로. 빈 항목도 제목을 보여 채울 자리를 남깁니다.
 *
 * 항목마다 따로 만듭니다. 문서 전체를 한 번에 변환하면 값이 빈 항목에는 문단이
 * 생기지 않아, 잠긴 제목만 줄줄이 붙고 글을 쓸 자리가 사라집니다.
 *
 * 잠금 클래스는 양식에 있는 라벨과 똑같은 제목에만 붙입니다. 사용자가 직접 만든
 * 제목까지 잠그면 자기가 쓴 것을 못 고치게 됩니다.
 */
export function toHtml(template: ReportTemplate, values: Record<string, string>): DocumentHtml {
  const filled = template.fields.filter((field) => (values[field.id] ?? '').trim())

  if (filled.length === 0) return { html: '<p></p>', sections: [] }

  // 자유로 쓴 글 한 덩어리는 제목을 달지 않습니다. 백지로 시작해 쓴 문서가 다시
  // 열었을 때 없던 양식을 뒤집어쓰고 나타나면 쓴 사람이 놀랍니다.
  if (filled.length === 1 && filled[0].id === catchAllId(template)) {
    return { html: render(values[filled[0].id] ?? ''), sections: [] }
  }

  return {
    html: template.fields
      .map(
        (field) =>
          `<h2 class="${LOCKED_CLASS}">${field.label}</h2>${render(values[field.id] ?? '')}`,
      )
      .join(''),
    sections: template.fields.map((field) => field.id),
  }
}

/** TinyMCE 가 돌려준 HTML 을 문서(markdown) 로 되돌립니다. */
export function toMarkdown(html: string): string {
  return turndown.turndown(html).trim()
}

interface Section {
  label: string
  body: string
}

/** '## ' 로 시작하는 줄마다 끊습니다. 첫 제목 앞의 글은 label 이 빈 조각이 됩니다. */
function splitSections(markdown: string): Section[] {
  const sections: Section[] = []
  let current: Section = { label: '', body: '' }

  for (const line of markdown.split('\n')) {
    const match = /^##\s+(.*)$/.exec(line)
    if (match) {
      sections.push(current)
      current = { label: match[1].trim(), body: '' }
      continue
    }
    current.body += `${line}\n`
  }
  sections.push(current)

  return sections
}

export interface DocumentParse {
  values: Record<string, string>
  /** 문서에 있던 항목 제목 중 사라진 것. 하나라도 있으면 저장을 막습니다. */
  missingSections: string[]
}

/**
 * 문서를 항목별 값으로 되돌립니다.
 *
 * 제목 없이 쓴 글은 마지막 항목(특이사항) 으로 갑니다. 백지에 자유롭게 쓴 문서가
 * 여기로 오고, 다시 열 때 toHtml 이 같은 모양으로 되돌려 줍니다.
 *
 * 양식에 없는 제목(사용자가 직접 만든 것)은 버리지 않고 바로 앞 항목에 제목째로
 * 붙입니다. 쓴 글이 저장에서 소리 없이 사라지는 일이 없어야 합니다.
 *
 * @param sections 이 문서를 세울 때 그렸던 항목 제목의 id. 없던 제목까지 사라졌다고
 *                 할 수는 없으므로, 여기 있는 것만 검사합니다. 백지 문서는 비어 있고
 *                 그래서 아무것도 막지 않습니다.
 */
export function toValues(
  template: ReportTemplate,
  markdown: string,
  sections: string[] = [],
): DocumentParse {
  const byLabel = new Map(template.fields.map((field) => [field.label, field.id]))
  const values: Record<string, string> = Object.fromEntries(
    template.fields.map((field) => [field.id, '']),
  )
  const seen = new Set<string>()

  // 아직 아무 항목도 시작하지 않았으면 자유로 쓴 글로 봅니다.
  let target = catchAllId(template)

  for (const section of splitSections(markdown)) {
    const id = section.label ? byLabel.get(section.label) : undefined

    if (id !== undefined && !seen.has(id)) {
      seen.add(id)
      target = id
      values[id] = section.body.trim()
      continue
    }

    if (!target) continue
    const carried = section.label
      ? `${heading(section.label)}

${section.body}`
      : section.body
    values[target] = `${values[target]}

${carried}`.trim()
  }

  const expected = new Set(sections)

  return {
    values,
    missingSections: template.fields
      .filter((field) => expected.has(field.id) && !seen.has(field.id))
      .map((field) => field.label),
  }
}
