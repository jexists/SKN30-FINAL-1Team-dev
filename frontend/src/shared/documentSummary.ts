/**
 * 자료요약(자료요약 Agent)이 만든 마크다운을 화면에 올리기 전에 다듬는다.
 *
 * 자료실 드로어와 브리핑이 같은 요약을 보여 주므로 규칙도 한 곳에 둔다. 브리핑이 이 함수를
 * 쓰지 않고 원문을 그대로 흘렸을 때 `## 핵심 요약` 같은 마크다운 기호가 글자로 보였다.
 */

/** 새 요약은 서버에서 만들지 않지만, 이미 저장된 구버전 요약에는 남아 있는 섹션이다. */
const HIDDEN_HEADINGS = new Set(['## 추출 필드', '## 출처'])
const HIDDEN_TITLES = new Set(['# 문서 요약', '# 문서요약'])

export function summaryWithoutHiddenSections(markdown: string): string {
  const lines = markdown.split('\n')
  const visibleLines: string[] = []
  let hiding = false

  for (const line of lines) {
    // 새 요약은 제목을 만들지 않지만, 구버전의 제목도 화면에서는 표시하지 않는다.
    if (HIDDEN_TITLES.has(line.trim())) continue
    if (/^#{1,2}\s+/.test(line)) hiding = HIDDEN_HEADINGS.has(line.trim())
    if (!hiding) visibleLines.push(line)
  }
  return visibleLines.join('\n')
}
