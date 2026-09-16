// 브리핑 글을 화면에 올릴 때 쓰는 표시 규칙. 한 벌만 두고 평문·스트림 양쪽이 같이 씁니다.
import { Fragment, type ReactNode } from 'react'

import type { CitedRange } from './briefingCitations'
import styles from './RecordDrawer.module.scss'

/**
 * 브리핑이 `[[ ]]` 로 감싼 "사람이 확인해야 할 값"을 표시로 바꿉니다.
 *
 * 마커가 없거나 짝이 안 맞아도 그냥 평문이 되도록 두었습니다. LLM 출력이라 형식이
 * 어긋날 수 있는데, 그때 글이 깨지는 것보다 강조가 빠지는 편이 낫습니다. 짝이 안 맞아
 * 남은 대괄호는 화면에 새지 않도록 지웁니다 — 타자 치듯 펴는 중에는 닫는 짝이 아직
 * 오지 않은 상태가 늘 있습니다.
 */
export function highlightChecks(summary?: string) {
  if (!summary) return null
  return summary.split(/\[\[(.+?)\]\]/g).map((part, index) =>
    index % 2 === 1 ? (
      <mark key={index} className={styles.check}>
        {part}
      </mark>
    ) : (
      part.replace(/\[\[|\]\]/g, '')
    ),
  )
}

/**
 * 브리핑 본문 한 줄. 문서에서 온 문장에 형광펜을 긋고, 그 안팎에서 확인값 강조를 그대로
 * 이어 갑니다.
 *
 * @param ranges 형광펜을 그을 자리(briefingCitations.citedRanges). 비어 있으면 지금까지와
 *   똑같이 확인값만 강조합니다 — 인용을 못 찾은 브리핑도 글이 달라 보이지 않아야 합니다.
 * @param marker 칠한 문장 끝에 붙일 것. 원문을 여는 작은 아이콘이 여기로 들어옵니다.
 *   형광펜 **안**에 넣어야 아이콘이 그 문장에 딸린 것으로 읽히고, 줄이 바뀔 때도 문장을
 *   따라갑니다.
 */
export function briefingBody(
  text: string,
  ranges: CitedRange[],
  marker?: (range: CitedRange) => ReactNode,
): ReactNode {
  if (ranges.length === 0) return highlightChecks(text)
  const parts: ReactNode[] = []
  let at = 0
  ranges.forEach((range, index) => {
    if (range.start > at) {
      parts.push(
        <Fragment key={`plain-${index}`}>{highlightChecks(text.slice(at, range.start))}</Fragment>,
      )
    }
    parts.push(
      <mark key={`cited-${index}`} className={styles.cited}>
        {highlightChecks(text.slice(range.start, range.end))}
        {range.done && marker?.(range)}
      </mark>,
    )
    at = range.end
  })
  if (at < text.length) {
    parts.push(<Fragment key="plain-tail">{highlightChecks(text.slice(at))}</Fragment>)
  }
  return parts
}
