import DocumentSummaryView from '@/components/DocumentSummaryView'
import type { BriefingDocument } from '@/types/agenda'

import styles from './RecordDrawer.module.scss'

/**
 * 옆 패널의 '요약' 탭. 브리핑 응답에 이미 실려 온 것만 그려 기다릴 것이 없습니다.
 *
 * 검색이 집어 온 구절은 세우지 않습니다. 원문에서 잘라 온 토막이라 표가 깨지고 인식이
 * 어긋난 채로 보여, 자료요약 Agent 가 만든 글보다 읽히지 않았습니다. 브리핑이 어느
 * 대목을 보고 썼는지는 본문의 형광펜과 그 끝의 원문 링크가 말합니다.
 */
export default function BriefingSourceSummary({ document }: { document: BriefingDocument }) {
  return (
    <div className={styles.summaryPane}>
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
