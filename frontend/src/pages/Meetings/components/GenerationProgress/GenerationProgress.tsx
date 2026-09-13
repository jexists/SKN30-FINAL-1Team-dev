// 서버의 실제 단계와 아직 검토되지 않은 문자열만 표시합니다. 저장·편집기는 별도입니다.
import { RefreshIcon } from '@/components/icons'
import type { MeetingPreview, MeetingProgress, MeetingStageResult } from '@/types'

import styles from './GenerationProgress.module.scss'
import { previewLabel, progressModel } from './progressModel'
import StageResults from './StageResults'

interface Props {
  progress?: MeetingProgress | null
  preview?: MeetingPreview
  previews?: MeetingPreview[]
  stageResults?: MeetingStageResult[]
  showStages?: boolean
  reportKind?: 'meeting' | 'period'
}

export default function GenerationProgress({
  progress,
  preview,
  previews,
  stageResults,
  showStages = true,
  reportKind = 'meeting',
}: Props) {
  const model = progressModel(progress, reportKind)
  const visiblePreviews = [
    ...(previews ?? []),
    ...(preview &&
    !(previews ?? []).some(
      (item) => item.revision === preview.revision && item.section === preview.section,
    )
      ? [preview]
      : []),
  ]
  return (
    <div className={styles.root}>
      <div className={styles.head} role="status" aria-live="polite">
        <RefreshIcon className={styles.spin} width={16} height={16} aria-hidden="true" />
        <p className={styles.headline}>
          {model.label}
          {progress?.stage === 'report_review' && progress.review_attempt != null && (
            <span>
              {' '}
              · 검토 {progress.review_attempt}
              {progress.review_limit ? `/${progress.review_limit}` : ''}회
            </span>
          )}
        </p>
        {progress?.phase_counts && <span aria-label="현재 단계 진행 수">{model.countLabel}</span>}
      </div>
      <ol aria-label="보고서 진행 단계">
        {model.steps.map((step) => (
          <li key={step} aria-current={step === model.currentStep ? 'step' : undefined}>
            {step}
          </li>
        ))}
      </ol>

      {visiblePreviews.length ? (
        <div className={styles.blocks}>
          {visiblePreviews.map((item) => (
            <div className={styles.preview} key={`${item.section}:${item.sales_deal_id ?? ''}`}>
              <p className={styles.draftLabel}>{previewLabel(item)}</p>
              <p className={styles.body}>{item.body || '내용을 확인하고 있습니다.'}</p>
            </div>
          ))}
          <p className={styles.notice}>
            검토 중 문장이 바뀔 수 있습니다. 완료 후에만 최종 보고서에 적용됩니다.
          </p>
        </div>
      ) : (
        <p className={styles.activity}>현재 단계 결과를 확인하고 있습니다.</p>
      )}
      {showStages && (
        <StageResults
          progress={{
            ...(progress ?? {
              run_id: '',
              status_code: 'running',
              stage: 'starting',
              previews: [],
            }),
            stage_results: stageResults,
          }}
        />
      )}
      {model.recoveryLabel && <p className={styles.recovery}>{model.recoveryLabel}</p>}
    </div>
  )
}
