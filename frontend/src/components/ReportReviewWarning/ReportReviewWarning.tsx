import styles from './ReportReviewWarning.module.scss'

interface Issue {
  action?: unknown
}

interface Review {
  review_required?: unknown
  review_incomplete?: unknown
  review_notes_may_predate_draft?: unknown
  issues?: unknown
}

export default function ReportReviewWarning({
  evidence,
}: {
  evidence: Record<string, unknown> | null | undefined
}) {
  const review = evidence?.report_review as Review | undefined
  const actions = Array.isArray(review?.issues)
    ? review.issues
        .map((issue) => (issue as Issue)?.action)
        .filter((action): action is string => typeof action === 'string' && action.trim() !== '')
    : []
  const historical = review?.review_notes_may_predate_draft === true && actions.length > 0
  if (review?.review_required !== true && !historical) return null
  return (
    <aside className={styles.warning} role="status">
      <strong>
        {review.review_incomplete === true
          ? 'AI 초안 검토를 끝내지 못했습니다. 최종 본문을 확인한 뒤 제출해 주세요.'
          : historical
            ? '자동 수정 전 AI 초안 검토 메모입니다. 최종 본문을 확인한 뒤 제출해 주세요.'
            : 'AI 초안 검토에서 확인한 내용입니다. 최종 본문을 확인한 뒤 제출해 주세요.'}
      </strong>
      {actions.length > 0 && (
        <ul>
          {actions.map((action, index) => (
            <li key={`${index}-${action}`}>{action}</li>
          ))}
        </ul>
      )}
    </aside>
  )
}
