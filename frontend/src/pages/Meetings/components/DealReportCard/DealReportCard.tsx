import { type StatusTone } from '@/components/StatusBadge'
import type { SalesDeal } from '@/pages/Deals/useSalesDeals'
import { isAuthorEditableReportStatus } from '@/shared/reports'
import type { MeetingDealRef, MeetingProgress } from '@/types'

import { isInsufficientDealPrediction } from '../../generatedDraft'
import type { DealDraftState } from '../../useMeetingDraft'
import DealCardHeader from '../DealCardHeader'
import ReportSheet from '../ReportSheet'

import styles from './DealReportCard.module.scss'

interface Props {
  dealId: string
  deal?: SalesDeal
  savedDeal?: MeetingDealRef
  draft: DealDraftState
  progress?: MeetingProgress | null
  saving: boolean
  generating: boolean
  canGenerate: boolean
  readOnly: boolean
  /** 화면 아래 [수정] 이 켜져 있는가. 잠긴 카드는 켜져 있어도 읽기로 남습니다. */
  editing?: boolean
  onTitleChange: (value: string) => void
  onChange: (body: string) => void
  onStartManual: () => void
  onGenerate: () => void
}

function assessmentBadge(draft: DealDraftState):
  | {
      label: string
      tone: StatusTone
      title?: string
    }
  | undefined {
  // 도는 중인 일은 배지가 아니라 활동 한 줄로 알립니다. 배지는 판정 결과 자리입니다.
  if (draft.analysisPhase === 'running') return undefined
  if (isInsufficientDealPrediction(draft.analysisError)) {
    return { label: '판단 정보 부족', tone: 'neutral' }
  }
  if (draft.analysisPhase === 'failed') {
    return { label: 'ML 분석 실패', tone: 'red', title: draft.analysisError ?? undefined }
  }
  if (draft.analysisPhase !== 'completed' || !draft.assessment) {
    return { label: 'ML 분석 대기', tone: 'neutral' }
  }

  const probability = `${Math.round(draft.assessment.high_probability * 100)}%`
  return draft.assessment.label === 'high'
    ? {
        label: `성사 가능성 높음 · ${probability}`,
        tone: 'green',
        title: `ML 모델 ${draft.assessment.model_version}`,
      }
    : {
        label: `관찰 필요 · ${probability}`,
        tone: 'orange',
        title: `ML 모델 ${draft.assessment.model_version}`,
      }
}

export default function DealReportCard({
  dealId,
  deal,
  savedDeal,
  draft,
  progress,
  saving,
  generating,
  canGenerate,
  readOnly,
  editing = false,
  onTitleChange,
  onChange,
  onStartManual,
  onGenerate,
}: Props) {
  const badge = assessmentBadge(draft)
  const dealLabel = deal?.no ?? savedDeal?.label ?? dealId
  const dealTitle = deal ? deal.title.trim() || deal.product : savedDeal?.note
  const editable = isAuthorEditableReportStatus(draft.statusCode)
  const locked = !editable || readOnly || generating || saving
  const generationDisabled = !isAuthorEditableReportStatus(draft.statusCode) || !canGenerate

  return (
    <article className={styles.card}>
      <DealCardHeader newTab dealId={dealId} label={dealLabel} note={dealTitle} badge={badge} />

      <div className={styles.body}>
        <ReportSheet
          embedded
          phase={draft.phase}
          titleId={`report-title-${dealId}`}
          title={draft.title}
          onTitleChange={onTitleChange}
          body={draft.values.body ?? ''}
          docKey={draft.docKey}
          onChange={onChange}
          evidence={draft.evidence}
          generationProgress={progress}
          generationPreview={progress?.previews.find(
            (preview) => preview.section === 'deal' && preview.sales_deal_id === dealId,
          )}
          generationError={draft.generationError}
          onRetryGenerate={onGenerate}
          generationDisabled={generationDisabled}
          locked={locked}
          editing={editing}
          saving={saving || generating}
          onStartManual={onStartManual}
        />
      </div>
    </article>
  )
}
