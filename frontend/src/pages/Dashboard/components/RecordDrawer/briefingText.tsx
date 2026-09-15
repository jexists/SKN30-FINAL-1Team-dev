// 브리핑 글을 화면에 올릴 때 쓰는 표시 규칙. 한 벌만 두고 평문·스트림 양쪽이 같이 씁니다.
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
