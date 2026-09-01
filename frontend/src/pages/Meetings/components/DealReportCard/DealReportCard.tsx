import { useId, useState } from 'react'

import { ChevronDownIcon } from '@/components/icons'
import StageChip from '@/components/StageChip'
import StatusBadge, { type StatusTone } from '@/components/StatusBadge'
import type { SalesDeal } from '@/pages/Deals/useSalesDeals'
import type { MeetingDealRef, MeetingProgress, ReportTemplate } from '@/types'

import type { DealDraftState } from '../../useMeetingDraft'
import AiOriginalPanel from '../AiOriginalPanel'
import ReportSheet from '../ReportSheet'

import styles from './DealReportCard.module.scss'

interface Props {
  dealId: string
  deal?: SalesDeal
  savedDeal?: MeetingDealRef
  draft: DealDraftState
  progress?: MeetingProgress | null
  template: ReportTemplate
  when: string
  saving: boolean
  generating: boolean
  canGenerate: boolean
  readOnly: boolean
  onTitleChange: (value: string) => void
  onChange: (values: Record<string, string>, missingSections: string[]) => void
  onRestoreSections: () => void
  onStartManual: () => void
  onApplyAi: () => void
  onGenerate: () => void
}

function assessmentBadge(draft: DealDraftState): {
  label: string
  tone: StatusTone
  title?: string
} {
  if (draft.analysisPhase === 'running') return { label: 'ML 분석 중', tone: 'blue' }
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
  template,
  when,
  saving,
  generating,
  canGenerate,
  readOnly,
  onTitleChange,
  onChange,
  onRestoreSections,
  onStartManual,
  onApplyAi,
  onGenerate,
}: Props) {
  const [open, setOpen] = useState(true)
  const bodyId = useId()
  const badge = assessmentBadge(draft)
  const dealLabel = deal?.no ?? savedDeal?.label ?? dealId
  const dealTitle = deal ? deal.title.trim() || deal.product : savedDeal?.note
  const editable = draft.statusCode === 'draft' || draft.statusCode === 'changes_requested'
  const locked = !editable || readOnly || generating || saving
  const generationDisabled = draft.statusCode !== 'draft' || !canGenerate
  const hasAiOriginal = Object.keys(draft.aiValues).length > 0

  return (
    <article className={styles.card}>
      <button
        type="button"
        className={`${styles.header} ${open ? styles.isOpen : ''}`}
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => setOpen((value) => !value)}
      >
        <span className={styles.identity}>
          <ChevronDownIcon className={styles.caret} width={17} height={17} />
          <span className={styles.dealText}>
            <span className={styles.dealLine}>
              <strong>{dealLabel}</strong>
              {deal && <StageChip tone={deal.stageTone}>{deal.stageName}</StageChip>}
            </span>
            {dealTitle && <span className={styles.dealTitle}>{dealTitle}</span>}
          </span>
        </span>

        <span className={styles.result} title={badge.title}>
          <StatusBadge label={badge.label} tone={badge.tone} />
        </span>
      </button>

      <div id={bodyId} className={`${styles.body} ${open ? '' : styles.isClosed}`}>
        {hasAiOriginal && (
          <details className={styles.original}>
            <summary>
              AI 원본 보기
              {draft.pendingAi && <span>새 결과</span>}
            </summary>
            <AiOriginalPanel
              template={template}
              values={draft.aiValues}
              evidence={draft.aiEvidence}
              generatedAt={draft.aiGeneratedAt}
              pending={draft.pendingAi}
              disabled={locked || saving}
              onApply={onApplyAi}
            />
          </details>
        )}

        <ReportSheet
          embedded
          phase={draft.phase}
          template={template}
          titleId={`report-title-${dealId}`}
          title={draft.title}
          onTitleChange={onTitleChange}
          when={when}
          values={draft.values}
          docKey={draft.docKey}
          onChange={onChange}
          sectionIssues={draft.sectionIssues}
          onRestoreSections={onRestoreSections}
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
          hasAiOriginal={hasAiOriginal}
          onStartManual={onStartManual}
          onRegenerate={onGenerate}
          regenerateLabel="미팅 전체 다시 생성"
        />
      </div>
    </article>
  )
}
