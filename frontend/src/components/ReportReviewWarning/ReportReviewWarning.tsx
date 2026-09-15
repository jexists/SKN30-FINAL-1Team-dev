// AI 가 v2 최종본에 대해 평가한 참고 메모. 사용자가 제출 전에 확인할 목록입니다.
//
// 생성 중에는 검토·수정 단계 결과가 실시간으로 여기 쌓이고, 끝나면 최종 평가로
// 바뀝니다. final_evaluation이 있으면 그것을 보여주고, 없으면 기존 이슈를 표시합니다.
import { ChevronDownIcon } from '@/components/icons'

import styles from './ReportReviewWarning.module.scss'

interface Issue {
  action?: unknown
}

interface FinalEvaluation {
  summary?: string
  notes?: string[]
}

interface Review {
  review_required?: unknown
  review_incomplete?: unknown
  review_notes_may_predate_draft?: unknown
  issues?: unknown
  final_evaluation?: FinalEvaluation
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
  const evaluation = review?.final_evaluation
  const issueActions = Array.isArray(review?.issues)
    ? review.issues
        .map((issue) => (issue as Issue)?.action)
        .filter((action): action is string => typeof action === 'string' && action.trim() !== '')
    : []
  const live = notes?.filter((note) => note.trim() !== '') ?? []
  const evalNotes = evaluation?.notes?.filter((n) => n.trim() !== '') ?? []

  // 생성 중에는 live 메모, 완료 후에는 final_evaluation, 없으면 기존 이슈
  const actions = generating && live.length ? live : evalNotes.length ? evalNotes : issueActions
  const hasEvaluation = !generating && evalNotes.length > 0
  const historical = review?.review_notes_may_predate_draft === true && issueActions.length > 0
  if (!actions.length && review?.review_required !== true && !historical && !evaluation?.summary) {
    return null
  }

  const summary = generating
    ? `AI 초안 검토 메모 ${actions.length}건`
    : hasEvaluation
      ? evaluation!.summary!
      : review?.review_incomplete === true
        ? 'AI 초안 검토를 끝내지 못했습니다. 최종 본문을 확인한 뒤 제출해 주세요.'
        : historical
          ? '자동 수정 전 AI 초안 검토 메모입니다. 최종 본문을 확인한 뒤 제출해 주세요.'
          : 'AI 초안 검토에서 확인한 내용입니다. 최종 본문을 확인한 뒤 제출해 주세요.'

  return (
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
