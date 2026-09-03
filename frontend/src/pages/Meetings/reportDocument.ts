import TurndownService from 'turndown'

import { reportBodyHtml } from '@/shared/reportMarkdown'

const turndown = new TurndownService({
  headingStyle: 'atx',
  bulletListMarker: '-',
  emDelimiter: '_',
})

// Turndown 기본값의 목록 들여쓰기 세 칸을 사람이 쓴 한 칸으로 유지합니다.
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

turndown.addRule('lineBreak', {
  filter: 'br',
  replacement: () => '\n',
})

/** 저장된 Markdown 본문을 편집기에 넣을 HTML로 바꿉니다. */
export function toHtml(body: string): string {
  return reportBodyHtml(body)
}

/** 편집기 HTML을 canonical Markdown 본문으로 되돌립니다. */
export function toMarkdown(html: string): string {
  return turndown.turndown(html).trim()
}
