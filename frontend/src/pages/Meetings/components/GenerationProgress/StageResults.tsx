import type { MeetingProgress } from '@/types'

import styles from './GenerationProgress.module.scss'

export default function StageResults({ progress }: { progress?: MeetingProgress | null }) {
  const results = progress?.stage_results ?? []
  if (!results.length) return null
  const groups = ['content_analysis', 'prepare', 'review_initial', 'repair']
    .map((stage) => ({
      stage,
      items: results.filter((item) => item.stage === stage),
    }))
    .filter((group) => group.items.length)
  return (
    <section className={styles.results} aria-label="생성 과정 및 단계 결과">
      <h2 className={styles.resultsTitle}>생성 과정 · 자료 정리·검토 결과 {results.length}개</h2>
      {groups.map((group) => (
        <section key={group.stage} className={styles.stageResults}>
          <h3>
            {group.stage === 'prepare'
              ? '자료 정리'
              : group.stage === 'content_analysis'
                ? '근거 분류'
                : group.stage === 'repair'
                  ? '수정'
                  : '검토'}{' '}
            · {group.items.length}개
          </h3>
          <div className={styles.blocks}>
            {group.items.map((item) => (
              <p className={styles.body} key={item.key}>
                {item.body}
              </p>
            ))}
          </div>
        </section>
      ))}
    </section>
  )
}
