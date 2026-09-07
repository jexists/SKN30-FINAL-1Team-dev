import { marked, Renderer } from 'marked'

const escapeHtml = (value: string) =>
  value.replace(/[&<>"']/g, (character) => {
    const escaped: Record<string, string> = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }
    return escaped[character]
  })

const renderer = new Renderer()
renderer.html = ({ text }) => escapeHtml(text)
// 보고서에는 외부 링크·이미지가 필요하지 않습니다. 주소는 버리고 보이는 글자만 남깁니다.
renderer.link = ({ tokens }) => renderer.parser.parseInline(tokens)
renderer.image = ({ tokens }) => renderer.parser.parseInline(tokens)

/** 저장 본문을 raw HTML·외부 URL 없이 표시 가능한 HTML로 바꿉니다. */
export function reportBodyHtml(body: string): string {
  return body.trim() ? marked.parse(body, { async: false, breaks: true, renderer }) : '<p></p>'
}
