import { useId, useState } from 'react'
import { Link } from 'react-router'

import { ChevronDownIcon } from '@/components/icons'
import StatusBadge, { type StatusTone } from '@/components/StatusBadge'
import { dealDetailPath } from '@/constants/routes'
import type { SalesDeal } from '@/pages/Deals/useSalesDeals'
import { isAuthorEditableReportStatus } from '@/shared/reports'
import type { MeetingDealRef, MeetingProgress } from '@/types'

import { isInsufficientDealPrediction } from '../../generatedDraft'
import type { DealDraftState } from '../../useMeetingDraft'
import ReportSheet from '../ReportSheet'

import styles from './DealReportCard.module.scss'

interface Props {
  dealId: string
  deal?: SalesDeal
  savedDeal?: MeetingDealRef
  draft: DealDraftState
  progress?: MeetingProgress | null
  when: string
  saving: boolean
  generating: boolean
  canGenerate: boolean
  readOnly: boolean
  onTitleChange: (value: string) => void
  onChange: (body: string) => void
  onStartManual: () => void
  onGenerate: () => void
}

function assessmentBadge(draft: DealDraftState): {
  label: string
  tone: StatusTone
  title?: string
} {
  if (draft.analysisPhase === 'running') return { label: 'ML 분석 중', tone: 'blue' }
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
  when,
  saving,
  generating,
  canGenerate,
  readOnly,
  onTitleChange,
  onChange,
  onStartManual,
  onGenerate,
}: Props) {
  const [open, setOpen] = useState(true)
  const bodyId = useId()
  const badge = assessmentBadge(draft)
  const dealLabel = deal?.no ?? savedDeal?.label ?? dealId
  const dealTitle = deal ? deal.title.trim() || deal.product : savedDeal?.note
  const editable = isAuthorEditableReportStatus(draft.statusCode)
  const locked = !editable || readOnly || generating || saving
  const generationDisabled = !isAuthorEditableReportStatus(draft.statusCode) || !canGenerate

  return (
    <article className={styles.card}>
      <header className={`${styles.header} ${open ? styles.isOpen : ''}`}>
        <button
          type="button"
          className={styles.disclosure}
          aria-label={`${dealLabel} 보고서 ${open ? '접기' : '펼치기'}`}
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={() => setOpen((value) => !value)}
        >
          <ChevronDownIcon className={styles.caret} width={17} height={17} />
        </button>

        <Link
          className={styles.identity}
          to={dealDetailPath(dealId)}
          target="_blank"
          rel="noreferrer"
          aria-label={`${dealLabel} 딜 상세 새 탭에서 열기`}
        >
          <span className={styles.dealText}>
            <span className={styles.dealLine}>
              <strong>{dealLabel}</strong>
            </span>
            {dealTitle && <span className={styles.dealTitle}>{dealTitle}</span>}
          </span>
        </Link>

        <span className={styles.result} title={badge.title}>
          <StatusBadge label={badge.label} tone={badge.tone} />
        </span>
      </header>

      <div id={bodyId} className={`${styles.body} ${open ? '' : styles.isClosed}`}>
        <ReportSheet
          embedded
          phase={draft.phase}
          titleId={`report-title-${dealId}`}
          title={draft.title}
          onTitleChange={onTitleChange}
          when={when}
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
          saving={saving || generating}
          onStartManual={onStartManual}
          onRegenerate={onGenerate}
          regenerateLabel="미팅 전체 다시 생성"
        />
      </div>
    </article>
  )
}
