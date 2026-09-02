// 미팅 원문·공통 메모는 한 벌, 편집 중인 최종본·ML 결과는 딜마다 한 벌입니다.
import { useCallback, useEffect, useRef, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import { meetingFreeformTemplate } from '@/shared/meetings'
import useAttachments from '@/shared/useAttachments'
import type {
  AgendaItem,
  ApiReportStatus,
  DealAssessment,
  MeetingDealSection,
  MeetingProcessingOutput,
  MeetingProgress,
  MeetingReport,
  MeetingReview,
  MeetingSharedNotes,
  ReportGenerationInput,
  ReportTemplate,
} from '@/types'

import { generatedDealOf } from './generatedDraft'
import { meetingGenerationSeedOf } from './useMeetingReports'

export type MeetingPhase = 'idle' | 'generating' | 'ready'
export type AnalysisPhase = 'idle' | 'running' | 'completed' | 'failed'

export interface DealDraftState {
  reportId?: string
  reportVersion?: number
  statusCode: ApiReportStatus
  review: MeetingReview
  template: ReportTemplate
  phase: MeetingPhase
  title: string
  values: Record<string, string>
  evidence?: string
  touched: boolean
  docKey: number
  sectionIssues: string[]
  generationError: string | null
  analysisPhase: AnalysisPhase
  assessment?: DealAssessment
  analysisError: string | null
}

interface MeetingResultState {
  runId?: string
  shared?: MeetingSharedNotes
}

const emptyValues = (template: ReportTemplate) =>
  Object.fromEntries(template.fields.map((field) => [field.id, '']))
const isBlank = (values: Record<string, string>) =>
  Object.values(values).every((value) => !value.trim())

/** 제목만 고친 경우도 AI 재생성이 사람 수정을 덮기 전에 확인해야 합니다. */
export function hasMeetingDraftContent(
  salesDealIds: string[],
  draftsByDeal: Record<string, Pick<DealDraftState, 'values' | 'touched'> | undefined>,
  shared?: MeetingSharedNotes,
): boolean {
  return (
    salesDealIds.some((id) => {
      const draft = draftsByDeal[id]
      return draft?.touched || Object.values(draft?.values ?? {}).some((value) => value.trim())
    }) || Boolean(shared?.common_report || shared?.unassigned_report)
  )
}

/** 자유형 생성 본문만 바꾸고 기존 구조화 값은 그대로 보존합니다. */
export function mergeMeetingGeneratedValues(
  previous: Record<string, string>,
  body: string,
): Record<string, string> {
  return { ...previous, body }
}

function stateOf(
  fallbackTitle: string,
  saved?: MeetingReport,
  section?: MeetingDealSection,
): DealDraftState {
  const template = saved?.template ?? meetingFreeformTemplate
  const values = { ...emptyValues(template), ...section?.values }
  return {
    reportId: saved?.id,
    reportVersion: saved?.version,
    statusCode: saved?.apiStatus ?? 'draft',
    review: saved?.review ?? 'writing',
    template,
    phase: isBlank(values) ? 'idle' : 'ready',
    title: section?.title || fallbackTitle,
    values,
    evidence: section?.evidence,
    touched: false,
    docKey: 0,
    sectionIssues: [],
    generationError: section?.reportError ?? null,
    analysisPhase: section?.analysisError ? 'failed' : section?.assessment ? 'completed' : 'idle',
    assessment: section?.assessment,
    analysisError: section?.analysisError ?? null,
  }
}

function meetingResultOf(report?: MeetingReport): MeetingResultState | null {
  return report?.meetingShared
    ? {
        shared: report.meetingShared,
      }
    : null
}

export default function useMeetingDraft(
  item?: AgendaItem,
  savedReport?: MeetingReport,
  sourceReady = true,
) {
  const initializedAgendaId = useRef<string | null>(null)
  const [transcript, setTranscript] = useState('')
  const files = useAttachments((text) =>
    setTranscript((previous) => (previous.trim() ? previous.trim() + '\n\n' + text : text)),
  )
  const [salesDealIds, setSalesDealIds] = useState<string[]>([])
  const [draftsByDeal, setDraftsByDeal] = useState<Record<string, DealDraftState>>({})
  const [meetingResult, setMeetingResult] = useState<MeetingResultState | null>(null)
  // 스트리밍 중 문장은 미리보기로만 두고, 완료된 AgentRun 후보만 편집 상태에 올립니다.
  const [processingProgress, setProcessingProgress] = useState<MeetingProgress | null>(null)
  const { setAttachments, setAttachmentError } = files
  const fallbackTitle = item?.title ?? ''

  const initialize = useCallback(() => {
    const ids = [...new Set(savedReport?.dealSections.map((section) => section.salesDealId) ?? [])]
    if (ids.length === 0 && item?.salesDealId) ids.push(item.salesDealId)
    const result = meetingResultOf(savedReport)
    setTranscript(savedReport?.transcript ?? '')
    setAttachments(savedReport?.attachments ?? [])
    setSalesDealIds(ids)
    setDraftsByDeal(
      Object.fromEntries(
        ids.map((dealId) => [
          dealId,
          stateOf(
            fallbackTitle,
            savedReport,
            savedReport?.dealSections.find((section) => section.salesDealId === dealId),
          ),
        ]),
      ),
    )
    setMeetingResult(result)
    setProcessingProgress(null)
    setAttachmentError(null)
  }, [savedReport, item?.salesDealId, fallbackTitle, setAttachments, setAttachmentError])

  useEffect(() => {
    // Fast Refresh가 와도 같은 미팅의 편집/실행 상태는 유지합니다.
    // 최초 자료를 모두 받은 시점 또는 다른 미팅으로 이동한 때에만 서버 값으로 시작합니다.
    if (!sourceReady || !item?.id || initializedAgendaId.current === item.id) return
    initializedAgendaId.current = item.id
    initialize()
  }, [sourceReady, item?.id, initialize])

  const updateDeal = useCallback(
    (dealId: string, update: (draft: DealDraftState) => DealDraftState) => {
      setDraftsByDeal((previous) => ({
        ...previous,
        [dealId]: update(previous[dealId] ?? stateOf(fallbackTitle)),
      }))
    },
    [fallbackTitle],
  )

  const toggleSalesDeal = useCallback(
    (dealId: string) => {
      setSalesDealIds((previous) =>
        previous.includes(dealId) ? previous.filter((id) => id !== dealId) : [...previous, dealId],
      )
      setDraftsByDeal((previous) =>
        previous[dealId] ? previous : { ...previous, [dealId]: stateOf(fallbackTitle) },
      )
    },
    [fallbackTitle],
  )

  const restoreGenerationInput = useCallback(
    (input: ReportGenerationInput) => {
      const restored = meetingGenerationSeedOf(input)
      setTranscript(restored.transcript)
      setAttachments(restored.attachments)
      setAttachmentError(null)
      setSalesDealIds(restored.salesDealIds)
      setDraftsByDeal((previous) =>
        Object.fromEntries(
          restored.salesDealIds.map((dealId) => {
            const current = previous[dealId] ?? stateOf(fallbackTitle)
            return [
              dealId,
              {
                ...current,
                template: restored.template,
                values: { ...emptyValues(restored.template), ...current.values },
              },
            ]
          }),
        ),
      )
    },
    [fallbackTitle, setAttachments, setAttachmentError],
  )

  const beginGeneration = useCallback(
    (dealIds: string[]) => {
      setProcessingProgress(null)
      setSalesDealIds((previous) => [...new Set([...previous, ...dealIds])])
      for (const id of dealIds)
        updateDeal(id, (draft) => ({
          ...draft,
          phase: 'generating',
          generationError: null,
          analysisPhase: 'running',
          analysisError: null,
        }))
    },
    [updateDeal],
  )

  // AgentRun 후보를 편집 상태에 직접 올립니다. 덮어쓸지는 실행 전에 화면이 확인합니다.
  const acceptGenerated = useCallback(
    (runId: string, output: MeetingProcessingOutput) => {
      setProcessingProgress(null)
      const dealIds = [...new Set(output.evidence.selected_deal_ids)]
      setSalesDealIds(dealIds)
      setDraftsByDeal((previous) =>
        Object.fromEntries(
          dealIds.map((dealId) => {
            const current = previous[dealId] ?? stateOf(fallbackTitle)
            const generated = generatedDealOf(output, dealId)
            const reportError = output.errors.report_writing
            return [
              dealId,
              {
                ...current,
                ...(generated.report
                  ? {
                      title: generated.report.title ?? fallbackTitle,
                      values: mergeMeetingGeneratedValues(current.values, generated.report.body),
                      evidence: undefined,
                      touched: false,
                      sectionIssues: [],
                      docKey: current.docKey + 1,
                      phase: 'ready' as const,
                    }
                  : { phase: isBlank(current.values) ? ('idle' as const) : ('ready' as const) }),
                generationError: generated.report
                  ? null
                  : reportError || '보고서 생성에 실패했습니다. 기존 작성 내용은 유지됩니다.',
                analysisPhase: generated.assessment
                  ? ('completed' as const)
                  : generated.analysisError
                    ? ('failed' as const)
                    : ('idle' as const),
                assessment: generated.assessment,
                analysisError: generated.analysisError ?? null,
              },
            ]
          }),
        ),
      )
      setMeetingResult({
        runId,
        shared: output.reports
          ? {
              common_report: output.reports.common_report,
              unassigned_report: output.reports.unassigned_report,
            }
          : undefined,
      })
    },
    [fallbackTitle],
  )

  const generationFailed = useCallback(
    (dealIds: string[], reason: unknown) => {
      setProcessingProgress(null)
      for (const id of dealIds)
        updateDeal(id, (draft) => ({
          ...draft,
          phase: isBlank(draft.values) ? 'idle' : 'ready',
          generationError: errorMessage(reason, '미팅 처리를 완료하지 못했습니다.'),
          analysisPhase: draft.assessment ? 'completed' : 'failed',
          analysisError: draft.assessment ? null : '새 분석 결과를 받지 못했습니다.',
        }))
    },
    [updateDeal],
  )

  return {
    transcript,
    setTranscript,
    attachments: files.attachments,
    addAttachments: files.addAttachments,
    removeAttachment: files.removeAttachment,
    attachmentError: files.attachmentError,
    salesDealIds,
    toggleSalesDeal,
    restoreGenerationInput,
    draftsByDeal,
    meetingResult,
    processingProgress,
    receiveProgress: setProcessingProgress,
    setTitle: (id: string, title: string) =>
      updateDeal(id, (draft) => ({ ...draft, title, touched: true })),
    applyDocument: (id: string, values: Record<string, string>, sectionIssues: string[]) =>
      updateDeal(id, (draft) => ({ ...draft, values, sectionIssues, touched: true })),
    restoreSections: (id: string) =>
      updateDeal(id, (draft) => ({
        ...draft,
        sectionIssues: [],
        docKey: draft.docKey + 1,
      })),
    startManual: (id: string) => updateDeal(id, (draft) => ({ ...draft, phase: 'ready' })),
    beginGeneration,
    acceptGenerated,
    generationFailed,
    setShared: (commonBody: string, unassignedBody: string) =>
      setMeetingResult((current) =>
        current
          ? {
              ...current,
              shared: {
                common_report: current.shared?.common_report
                  ? { ...current.shared.common_report, body: commonBody }
                  : null,
                unassigned_report: current.shared?.unassigned_report
                  ? { ...current.shared.unassigned_report, body: unassignedBody }
                  : null,
              },
            }
          : current,
      ),
    canGenerate:
      transcript.trim().length > 0 &&
      salesDealIds.length > 0 &&
      !files.attachments.some((attachment) => attachment.state === 'analyzing'),
  }
}
