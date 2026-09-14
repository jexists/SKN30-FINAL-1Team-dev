// AI 가 제 초안에서 스스로 짚은 것들. 쓰는 사람이 제출 전에 확인할 목록입니다.
//
// 생성 중에는 검토·수정 단계 결과가 실시간으로 여기 쌓이고, 끝나면 실행 근거의
// 최종 메모로 바뀝니다. 둘은 같은 말을 하는 같은 자리이므로 판을 나누지 않습니다.
import { ChevronDownIcon } from '@/components/icons'

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

interface Props {
  evidence: Record<string, unknown> | null | undefined
  /** 생성 중 도착한 검토·수정 메모. 있으면 이쪽이 먼저입니다. */
  notes?: string[]
  /** 생성 중에는 펼쳐 두고, 끝나는 순간 한 줄로 접습니다. */
  generating?: boolean
}

export default function ReportReviewWarning({ evidence, notes, generating = false }: Props) {
  const review = evidence?.report_review as Review | undefined
  const issueActions = Array.isArray(review?.issues)
    ? review.issues
        .map((issue) => (issue as Issue)?.action)
        .filter((action): action is string => typeof action === 'string' && action.trim() !== '')
    : []
  const live = notes?.filter((note) => note.trim() !== '') ?? []
  const actions = generating && live.length ? live : issueActions
  const historical = review?.review_notes_may_predate_draft === true && issueActions.length > 0
  // 생성 중에는 근거가 아직 없습니다. 도착한 메모만으로도 열 이유가 됩니다.
  if (!actions.length && review?.review_required !== true && !historical) return null

  const summary = generating
    ? `AI 초안 검토 메모 ${actions.length}건`
    : review?.review_incomplete === true
      ? 'AI 초안 검토를 끝내지 못했습니다. 최종 본문을 확인한 뒤 제출해 주세요.'
      : historical
        ? '자동 수정 전 AI 초안 검토 메모입니다. 최종 본문을 확인한 뒤 제출해 주세요.'
        : 'AI 초안 검토에서 확인한 내용입니다. 최종 본문을 확인한 뒤 제출해 주세요.'

  return (
    /*
     * key 로 다시 세웁니다. 생성이 끝나는 순간 한 번 접히고, 그 뒤로 사용자가
     * 여닫은 상태는 건드리지 않습니다 — open 을 붙들면 열어 둔 것이 도로 닫힙니다.
     */
    <details
      key={generating ? 'live' : 'settled'}
      className={styles.warning}
      open={generating}
      role="note"
    >
      <summary className={styles.summary}>
        <ChevronDownIcon className={styles.chevron} width={14} height={14} aria-hidden="true" />
        <strong>{summary}</strong>
      </summary>
      {actions.length > 0 && (
        <ul>
          {actions.map((action, index) => (
            <li key={`${index}-${action}`}>{action}</li>
          ))}
        </ul>
      )}
    </details>
  )
}
