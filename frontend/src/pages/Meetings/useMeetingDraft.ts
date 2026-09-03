// 미팅 원문·공통 메모는 한 벌, 편집 중인 최종본·ML 결과는 딜마다 한 벌입니다.
import { useCallback, useEffect, useRef, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
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
  phase: MeetingPhase
  title: string
  values: Record<string, string>
  evidence?: string
  touched: boolean
  docKey: number
  generationError: string | null
  analysisPhase: AnalysisPhase
  assessment?: DealAssessment
  analysisError: string | null
}

export interface MeetingResultState {
  runId?: string
  shared?: MeetingSharedNotes
}

/** 원문·첨부·선택 딜이 바뀌면 이전 입력의 AgentRun을 최종 제출에 연결하지 않습니다. */
export function invalidateMeetingGeneration(
  result: MeetingResultState | null,
): MeetingResultState | null {
  return result?.runId ? { ...result, runId: undefined } : result
}

export const isMeetingBodyBlank = (values: Record<string, string>) => !(values.body ?? '').trim()

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

/** 미팅 생성 후보도 canonical 본문 한 칸만 받습니다. */
export function mergeMeetingGeneratedValues(body: string): Record<string, string> {
  return { body }
}

function stateOf(
  fallbackTitle: string,
  saved?: MeetingReport,
  section?: MeetingDealSection,
): DealDraftState {
  const values = { body: section?.values.body ?? '' }
  return {
    reportId: saved?.id,
    reportVersion: saved?.version,
    statusCode: saved?.apiStatus ?? 'draft',
    review: saved?.review ?? 'writing',
    phase: isMeetingBodyBlank(values) ? 'idle' : 'ready',
    title: section?.title || fallbackTitle,
    values,
    evidence: section?.evidence,
    touched: false,
    docKey: 0,
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
  const [salesDealIds, setSalesDealIds] = useState<string[]>([])
  const [draftsByDeal, setDraftsByDeal] = useState<Record<string, DealDraftState>>({})
  const [meetingResult, setMeetingResult] = useState<MeetingResultState | null>(null)
  const invalidateGeneration = useCallback(() => setMeetingResult(invalidateMeetingGeneration), [])
  const changeTranscript = useCallback(
    (value: string) => {
      setTranscript(value)
      invalidateGeneration()
    },
    [invalidateGeneration],
  )
  const files = useAttachments((text) => {
    setTranscript((previous) => (previous.trim() ? previous.trim() + '\n\n' + text : text))
    invalidateGeneration()
  })
  // 스트리밍 중 문장은 미리보기로만 두고, 완료된 AgentRun 후보만 편집 상태에 올립니다.
  const [processingProgress, setProcessingProgress] = useState<MeetingProgress | null>(null)
  const {
    addAttachments: addFiles,
    removeAttachment: removeFile,
    setAttachments,
    setAttachmentError,
  } = files
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
      invalidateGeneration()
      setSalesDealIds((previous) =>
        previous.includes(dealId) ? previous.filter((id) => id !== dealId) : [...previous, dealId],
      )
      setDraftsByDeal((previous) =>
        previous[dealId] ? previous : { ...previous, [dealId]: stateOf(fallbackTitle) },
      )
    },
    [fallbackTitle, invalidateGeneration],
  )

  const addAttachments = useCallback(
    (picked: FileList | File[]) => {
      invalidateGeneration()
      return addFiles(picked)
    },
    [addFiles, invalidateGeneration],
  )
  const removeAttachment = useCallback(
    (id: string) => {
      invalidateGeneration()
      removeFile(id)
    },
    [invalidateGeneration, removeFile],
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
          restored.salesDealIds.map((dealId) => [
            dealId,
            previous[dealId] ?? stateOf(fallbackTitle),
          ]),
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
                      values: mergeMeetingGeneratedValues(generated.report.body),
                      evidence: undefined,
                      touched: false,
                      docKey: current.docKey + 1,
                      phase: 'ready' as const,
                    }
                  : {
                      phase: isMeetingBodyBlank(current.values)
                        ? ('idle' as const)
                        : ('ready' as const),
                    }),
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
          phase: isMeetingBodyBlank(draft.values) ? 'idle' : 'ready',
          generationError: errorMessage(reason, '미팅 처리를 완료하지 못했습니다.'),
          analysisPhase: draft.assessment ? 'completed' : 'failed',
          analysisError: draft.assessment ? null : '새 분석 결과를 받지 못했습니다.',
        }))
    },
    [updateDeal],
  )

  return {
    transcript,
    setTranscript: changeTranscript,
    attachments: files.attachments,
    addAttachments,
    removeAttachment,
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
    applyDocument: (id: string, body: string) =>
      updateDeal(id, (draft) => ({ ...draft, values: { body }, touched: true })),
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
