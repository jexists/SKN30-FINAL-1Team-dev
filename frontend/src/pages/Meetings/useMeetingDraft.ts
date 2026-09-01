// 미팅 원문·공통 메모는 한 벌, 최종본·AI 원본·ML 결과는 딜마다 한 벌입니다.
import { useCallback, useEffect, useRef, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import { meetingFreeformTemplate } from '@/shared/meetings'
import useAttachments from '@/shared/useAttachments'
import type {
  AgendaItem,
  ApiReportStatus,
  DealAssessment,
  MeetingEvidenceLedger,
  MeetingProgress,
  MeetingReport,
  MeetingReview,
  MeetingSharedNotes,
  ReportTemplate,
} from '@/types'

import { hasPendingAi, transcriptDigest } from './generatedDraft'

export type MeetingPhase = 'idle' | 'generating' | 'ready'
export type AnalysisPhase = 'idle' | 'running' | 'completed' | 'failed'

export interface DealDraftState {
  reportId?: string
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
  aiValues: Record<string, string>
  aiEvidence?: string
  aiGeneratedAt?: string
  pendingAi: boolean
  generationError: string | null
  analysisPhase: AnalysisPhase
  assessment?: DealAssessment
  analysisError: string | null
}

interface MeetingResultState {
  runId: string
  transcript: string
  evidence?: MeetingEvidenceLedger
  shared?: MeetingSharedNotes
}

const emptyValues = (template: ReportTemplate) =>
  Object.fromEntries(template.fields.map((field) => [field.id, '']))
const isBlank = (values: Record<string, string>) =>
  Object.values(values).every((value) => !value.trim())

function stateOf(fallbackTitle: string, saved?: MeetingReport): DealDraftState {
  const template = saved?.template ?? meetingFreeformTemplate
  const values = { ...emptyValues(template), ...saved?.values }
  const aiValues = saved?.aiValues ?? {}
  return {
    reportId: saved?.id,
    statusCode: saved?.apiStatus ?? 'draft',
    review: saved?.review ?? 'writing',
    template,
    phase: isBlank(values) ? 'idle' : 'ready',
    title: saved?.title ?? fallbackTitle,
    values,
    evidence: saved?.evidence,
    touched: false,
    docKey: 0,
    sectionIssues: [],
    aiValues,
    aiEvidence: saved?.aiEvidence,
    aiGeneratedAt: saved?.aiGeneratedAt,
    pendingAi: hasPendingAi(values, aiValues),
    generationError: saved?.reportError ?? null,
    analysisPhase: saved?.analysisError ? 'failed' : saved?.assessment ? 'completed' : 'idle',
    assessment: saved?.assessment,
    analysisError: saved?.analysisError ?? null,
  }
}

function meetingResultOf(reports: MeetingReport[]): MeetingResultState | null {
  const latest = reports
    .filter((report) => report.meetingRunId)
    .sort((a, b) =>
      (b.updatedAt ?? b.aiGeneratedAt ?? '').localeCompare(a.updatedAt ?? a.aiGeneratedAt ?? ''),
    )[0]
  return latest?.meetingRunId
    ? {
        runId: latest.meetingRunId,
        transcript: latest.transcript,
        evidence: latest.evidenceLedger,
        shared: latest.meetingShared,
      }
    : null
}

export default function useMeetingDraft(
  item?: AgendaItem,
  savedReports: MeetingReport[] = [],
  sourceReady = true,
) {
  const initializedAgendaId = useRef<string | null>(null)
  const [transcript, setTranscript] = useState('')
  const [hashedTranscript, setHashedTranscript] = useState<{ text: string; hash: string } | null>(
    null,
  )
  const transcriptSha256 = hashedTranscript?.text === transcript ? hashedTranscript.hash : null
  useEffect(() => {
    let cancelled = false
    void transcriptDigest(transcript)
      .then((hash) => {
        if (!cancelled) setHashedTranscript({ text: transcript, hash })
      })
      .catch(() => {
        /* 해시를 확인할 수 없으면 기존 근거 재배정을 허용하지 않습니다. */
      })
    return () => {
      cancelled = true
    }
  }, [transcript])
  const files = useAttachments((text) =>
    setTranscript((previous) => (previous.trim() ? previous.trim() + '\n\n' + text : text)),
  )
  const [salesDealIds, setSalesDealIds] = useState<string[]>([])
  const [draftsByDeal, setDraftsByDeal] = useState<Record<string, DealDraftState>>({})
  const [meetingResult, setMeetingResult] = useState<MeetingResultState | null>(null)
  // 전송 중 문장은 저장/AI원본과 분리합니다. 검증된 apply 응답만 draftsByDeal을 채웁니다.
  const [processingProgress, setProcessingProgress] = useState<MeetingProgress | null>(null)
  const { setAttachments, setAttachmentError } = files
  const fallbackTitle = item?.title ?? ''

  const initialize = useCallback(() => {
    const ids = [...new Set(savedReports.flatMap((report) => report.salesDealId ?? []))]
    if (ids.length === 0 && item?.salesDealId) ids.push(item.salesDealId)
    const result = meetingResultOf(savedReports)
    setTranscript(result?.transcript ?? savedReports[0]?.transcript ?? '')
    setAttachments(savedReports[0]?.attachments ?? [])
    setSalesDealIds(ids)
    setDraftsByDeal(
      Object.fromEntries(
        ids.map((dealId) => [
          dealId,
          stateOf(
            fallbackTitle,
            savedReports.find((report) => report.salesDealId === dealId),
          ),
        ]),
      ),
    )
    setMeetingResult(result)
    setProcessingProgress(null)
    setAttachmentError(null)
  }, [savedReports, item?.salesDealId, fallbackTitle, setAttachments, setAttachmentError])

  useEffect(() => {
    // 사전저장 후 재조회나 Fast Refresh가 와도 같은 미팅의 편집/실행 상태는 유지합니다.
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

  const bindReport = useCallback(
    (dealId: string, report: MeetingReport) =>
      updateDeal(dealId, (draft) => ({
        ...draft,
        reportId: report.id,
        statusCode: report.apiStatus ?? draft.statusCode,
        review: report.review,
      })),
    [updateDeal],
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

  // 서버 apply가 사람 최종본을 보존한 결과를 반환합니다. 생성 중 편집은 잠겨 있습니다.
  const acceptGenerated = useCallback(
    (reports: MeetingReport[], writingFailed = false) => {
      setProcessingProgress(null)
      for (const report of reports) {
        if (!report.salesDealId) continue
        updateDeal(report.salesDealId, (draft) => ({
          ...stateOf(fallbackTitle, report),
          docKey: draft.docKey + 1,
          generationError: writingFailed
            ? '보고서 생성에 실패했습니다. 기존 작성 내용은 유지됩니다.'
            : (report.reportError ?? null),
        }))
      }
      setMeetingResult(meetingResultOf(reports))
    },
    [fallbackTitle, updateDeal],
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
    transcriptSha256,
    setTranscript,
    attachments: files.attachments,
    addAttachments: files.addAttachments,
    removeAttachment: files.removeAttachment,
    attachmentError: files.attachmentError,
    salesDealIds,
    toggleSalesDeal,
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
    applyAi: (id: string) =>
      updateDeal(id, (draft) => ({
        ...draft,
        values: { ...draft.values, ...draft.aiValues },
        evidence: draft.aiEvidence,
        sectionIssues: [],
        docKey: draft.docKey + 1,
        pendingAi: false,
        phase: 'ready',
        touched: true,
      })),
    bindReport,
    beginGeneration,
    acceptGenerated,
    generationFailed,
    acceptShared: (reports: MeetingReport[]) => setMeetingResult(meetingResultOf(reports)),
    canGenerate:
      transcript.trim().length > 0 &&
      salesDealIds.length > 0 &&
      !files.attachments.some((attachment) => attachment.state === 'analyzing'),
  }
}
