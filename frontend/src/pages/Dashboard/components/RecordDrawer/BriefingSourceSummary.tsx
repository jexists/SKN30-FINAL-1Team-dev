import DocumentSummaryView from '@/components/DocumentSummaryView'
import type { BriefingDocument } from '@/types/agenda'

import styles from './RecordDrawer.module.scss'

/**
 * 옆 패널의 '요약' 탭. 브리핑 응답에 이미 실려 온 것만 그려 기다릴 것이 없습니다.
 *
 * 검색이 집어 온 구절을 먼저, 자료요약 Agent 가 만든 글을 뒤에 둡니다. 브리핑이 왜 이
 * 자료를 들고 왔는지가 먼저 읽혀야 요약을 볼지 원본을 열지 정할 수 있습니다.
 */
export default function BriefingSourceSummary({ document }: { document: BriefingDocument }) {
  const excerpts = document.excerpts ?? []
  return (
    <div className={styles.summaryPane}>
      {excerpts.length > 0 && (
        <section>
          <h4 className={styles.summaryPaneTitle}>브리핑이 참고한 부분</h4>
          {excerpts.map((excerpt, index) => (
            <blockquote className={styles.excerpt} key={index}>
              {excerpt.page_start && (
                <small>
                  {excerpt.page_start}페이지
                  {excerpt.page_end && excerpt.page_end !== excerpt.page_start
                    ? `–${excerpt.page_end}페이지`
                    : ''}
                </small>
              )}
              <p>{excerpt.content}</p>
            </blockquote>
          ))}
        </section>
      )}
      {document.summary_markdown && (
        <section>
          <h4 className={styles.summaryPaneTitle}>자료요약</h4>
          {/* BriefingDocument 에는 payload 가 없어 마크다운만 넘깁니다. */}
          <DocumentSummaryView markdown={document.summary_markdown} />
        </section>
      )}
    </div>
  )
}
