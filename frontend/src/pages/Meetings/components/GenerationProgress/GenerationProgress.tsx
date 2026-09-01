// 서버의 실제 단계와 아직 검토되지 않은 문자열만 표시합니다. 저장·편집기는 별도입니다.
import { RefreshIcon } from '@/components/icons'
import Skeleton from '@/components/Skeleton'
import type { MeetingPreview, MeetingProgress } from '@/types'

import styles from './GenerationProgress.module.scss'

interface Props {
  progress?: MeetingProgress | null
  preview?: MeetingPreview
  /** 채워질 항목 수. 자리표시자를 실제 보고서 길이에 맞춥니다. */
  fieldCount: number
}

const STAGE_LABELS: Record<string, string> = {
  starting: '미팅 처리 시작을 기다리는 중입니다',
  content_analysis: '미팅 원문과 딜 근거를 분석하는 중입니다',
  report_writing: '딜별 보고서를 작성하는 중입니다',
  report_review: '보고서 근거와 표현을 검토하는 중입니다',
  report_complete: '보고서 검토 완료 · 나머지 분석을 기다리는 중입니다',
  features: '딜별 특성과 ML 결과를 분석하는 중입니다',
  analysis_complete: 'ML 분석 완료 · 보고서 처리를 기다리는 중입니다',
}

export default function GenerationProgress({ progress, preview, fieldCount }: Props) {
  const label = progress
    ? (STAGE_LABELS[progress.stage] ?? '미팅 처리 결과를 기다리는 중입니다')
    : '미팅 처리를 준비하는 중입니다'
  return (
    <div className={styles.root}>
      <div className={styles.head} role="status" aria-live="polite">
        <RefreshIcon className={styles.spin} width={16} height={16} aria-hidden="true" />
        <p className={styles.headline}>
          {label}
          {progress?.stage === 'report_review' && progress.review_attempt != null && (
            <span>
              {' '}
              · 검토 {progress.review_attempt}
              {progress.review_limit ? `/${progress.review_limit}` : ''}회
            </span>
          )}
        </p>
      </div>

      {preview ? (
        <div className={styles.preview}>
          <p className={styles.draftLabel}>작성 중인 초안 · 검토 전</p>
          <p className={styles.body}>{preview.body || '문장을 작성하고 있습니다.'}</p>
          <p className={styles.notice}>
            검토 중 문장이 바뀔 수 있습니다. 완료 후에만 최종 보고서에 적용됩니다.
          </p>
        </div>
      ) : (
        <div className={styles.blocks}>
          {Array.from({ length: fieldCount }, (_, at) => (
            <Skeleton key={at} height={76} radius="var(--r-sm)" />
          ))}
        </div>
      )}
    </div>
  )
}
