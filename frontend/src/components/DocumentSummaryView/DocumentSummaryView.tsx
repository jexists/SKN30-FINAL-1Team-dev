import { useMemo } from 'react'

import { isEmptySummary, toSummaryModel } from './summaryModel'

import styles from './DocumentSummaryView.module.scss'

interface Props {
  /**
   * 서버가 저장한 구조화 요약(`summary_payload`). 검증되지 않은 JSON 이라 모델 쪽에서
   * 모양을 확인합니다. 마크다운만 있는 화면에서는 넘기지 않습니다.
   */
  payload?: unknown
  markdown: string | null
  className?: string
}

/**
 * 자료요약 Agent 의 결과를 그립니다.
 *
 * 요약은 성격이 다른 세 덩어리입니다 — 무엇에 대한 문서인가(도입), 문서에 무엇이 적혀
 * 있는가(주요 내용), 영업이 무엇을 봐야 하는가(참고사항·리스크). 한 색 한 크기의 불릿으로
 * 이어 놓으면 읽는 사람이 매번 처음부터 훑어야 합니다.
 *
 * 그래서 면도 구분선도 쓰지 않습니다. 요약은 훑어 읽는 글이라 선과 상자를 더할수록
 * 글보다 그것이 먼저 보입니다. 나누는 일은 여백이 하고, 구획 제목이 어디부터인지
 * 말하고, 영업 참고사항만 글자를 한 단 굵게 해서 앞에 세웁니다 — 주요 내용은 문서가
 * 말하는 것이고, 영업 참고사항은 담당자가 행동하는 것입니다.
 *
 * 구획 제목은 보고서 화면과 같은 표시를 씁니다(ReportView 의 막대와 꼬리선). 이 요약만의
 * 장식을 새로 만들면 같은 앱 안에서 혼자 다른 말투가 됩니다. 막대는 리스크에서만 빨강이고,
 * 그것이 요약 전체의 유일한 색입니다.
 *
 * 빈 항목은 자리를 만들지 않습니다. 리스크가 없는 문서에 "리스크 · 없음" 두 줄이 서면
 * 실제 리스크가 있는 문서와 한눈에 구별되지 않습니다.
 */
export default function DocumentSummaryView({ payload, markdown, className = '' }: Props) {
  const model = useMemo(() => toSummaryModel(payload, markdown), [payload, markdown])
  if (isEmptySummary(model)) return null

  return (
    <div className={`${styles.root} ${className}`.trim()}>
      {model.lead && <p className={styles.lead}>{model.lead}</p>}

      {model.keyPoints.length > 0 && (
        <section className={styles.section}>
          <h4 className={styles.heading}>주요 내용</h4>
          {/* 항목이 한글 장문이라 불릿 점이 줄바꿈마다 시선을 끊습니다.
              항목 사이 헤어라인이 같은 일을 조용히 합니다. */}
          <ul className={styles.points}>
            {model.keyPoints.map((point, index) => (
              <li key={index}>{point}</li>
            ))}
          </ul>
        </section>
      )}

      {model.salesRelevance.length > 0 && (
        <section className={styles.section}>
          <h4 className={styles.heading}>영업 참고사항</h4>
          <ul className={`${styles.points} ${styles.act}`}>
            {model.salesRelevance.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      {model.riskFlags.length > 0 && (
        <section className={styles.section}>
          <h4 className={`${styles.heading} ${styles.riskHeading}`}>리스크</h4>
          {/* 몇 건인지를 제목 옆 숫자로 따로 말하지 않습니다. 번호를 매기면 목록이
              스스로 세므로, 같은 것을 두 곳에서 말하지 않게 됩니다. */}
          <ol className={styles.risks}>
            {model.riskFlags.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ol>
        </section>
      )}
    </div>
  )
}
