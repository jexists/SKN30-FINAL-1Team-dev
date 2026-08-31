// 업무보고서 작성 화면의 상태입니다.
//
// 원문·첨부·선택 딜은 미팅에 한 벌이고, 최종 보고서·AI 원본·ML 결과는 딜마다 한 벌입니다.
// Report 한 행이 Deal 하나를 가리키므로 화면 상태도 dealId 를 키로 같은 경계를 지킵니다.
import { useCallback, useEffect, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import { analyzeMeetingReport, generateReportDraft } from '@/api/reportAgent'
import { meetingTemplate } from '@/shared/meetings'
import useAttachments from '@/shared/useAttachments'
import type {
  AgendaItem,
  AgentRunStatus,
  ApiReportStatus,
  DealAssessment,
  MeetingReport,
  MeetingReview,
  ReportTemplate,
} from '@/types'

import { mergeGeneratedValues } from './generatedDraft'

export type MeetingPhase = 'idle' | 'generating' | 'ready'
export type AnalysisPhase = 'idle' | 'running' | 'completed' | 'failed'

export interface DealDraftState {
  reportId?: string
  statusCode: ApiReportStatus
  review: MeetingReview
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

export interface GeneratedDealDraft {
  values: Record<string, string>
  evidence?: string
  aiValues: Record<string, string>
  aiEvidence?: string
  aiGeneratedAt: string
}

const emptyValues = (template: ReportTemplate) =>
  Object.fromEntries(template.fields.map((field) => [field.id, '']))

const isBlank = (template: ReportTemplate, values: Record<string, string>) =>
  template.fields.every((field) => !values[field.id]?.trim())

function stateOf(
  template: ReportTemplate,
  fallbackTitle: string,
  saved?: MeetingReport,
): DealDraftState {
  const values = saved ? { ...emptyValues(template), ...saved.values } : emptyValues(template)
  return {
    reportId: saved?.id,
    statusCode: saved?.apiStatus ?? 'draft',
    review: saved?.review ?? 'writing',
    phase: isBlank(template, values) ? 'idle' : 'ready',
    title: saved?.title ?? fallbackTitle,
    values,
    evidence: saved?.evidence,
    touched: false,
    docKey: 0,
    sectionIssues: [],
    aiValues: saved?.aiValues ?? {},
    aiEvidence: saved?.aiEvidence,
    aiGeneratedAt: saved?.aiGeneratedAt,
    pendingAi: false,
    generationError: null,
    analysisPhase: 'idle',
    assessment: undefined,
    analysisError: null,
  }
}

export default function useMeetingDraft(item?: AgendaItem, savedReports: MeetingReport[] = []) {
  const template = savedReports[0]?.template ?? meetingTemplate
  const [transcript, setTranscript] = useState('')
  // 음성에서 뽑은 글은 사람이 쓴 것을 덮지 않습니다. 있으면 아래에 붙입니다.
  const files = useAttachments((text) =>
    setTranscript((previous) => (previous.trim() ? `${previous.trim()}\n\n${text}` : text)),
  )
  const [salesDealIds, setSalesDealIds] = useState<string[]>([])
  const [draftsByDeal, setDraftsByDeal] = useState<Record<string, DealDraftState>>({})

  const { setAttachments, setAttachmentError } = files
  const fallbackTitle = item?.title ?? ''

  const reset = useCallback(() => {
    const ids = [...new Set(savedReports.flatMap((report) => report.salesDealId ?? []))]
    if (ids.length === 0 && item?.salesDealId) ids.push(item.salesDealId)

    setTranscript(savedReports[0]?.transcript ?? '')
    setAttachments(savedReports[0]?.attachments ?? [])
    setSalesDealIds(ids)
    setDraftsByDeal(
      Object.fromEntries(
        ids.map((dealId) => [
          dealId,
          stateOf(
            template,
            fallbackTitle,
            savedReports.find((report) => report.salesDealId === dealId),
          ),
        ]),
      ),
    )
    setAttachmentError(null)
  }, [savedReports, item?.salesDealId, template, fallbackTitle, setAttachments, setAttachmentError])

  useEffect(() => {
    reset()
  }, [reset])

  const updateDeal = useCallback(
    (dealId: string, update: (current: DealDraftState) => DealDraftState) => {
      setDraftsByDeal((previous) => {
        const current = previous[dealId] ?? stateOf(template, fallbackTitle)
        return { ...previous, [dealId]: update(current) }
      })
    },
    [template, fallbackTitle],
  )

  const toggleSalesDeal = useCallback(
    (dealId: string) => {
      setSalesDealIds((previous) =>
        previous.includes(dealId)
          ? previous.filter((one) => one !== dealId)
          : [...previous, dealId],
      )
      setDraftsByDeal((previous) =>
        previous[dealId] ? previous : { ...previous, [dealId]: stateOf(template, fallbackTitle) },
      )
    },
    [template, fallbackTitle],
  )

  const setTitle = useCallback(
    (dealId: string, title: string) =>
      updateDeal(dealId, (draft) => ({ ...draft, title, touched: true })),
    [updateDeal],
  )

  const applyDocument = useCallback(
    (dealId: string, values: Record<string, string>, sectionIssues: string[]) =>
      updateDeal(dealId, (draft) => ({
        ...draft,
        values,
        sectionIssues,
        touched: true,
      })),
    [updateDeal],
  )

  const restoreSections = useCallback(
    (dealId: string) =>
      updateDeal(dealId, (draft) => ({
        ...draft,
        sectionIssues: [],
        docKey: draft.docKey + 1,
      })),
    [updateDeal],
  )

  const startManual = useCallback(
    (dealId: string) => updateDeal(dealId, (draft) => ({ ...draft, phase: 'ready' })),
    [updateDeal],
  )

  const applyAi = useCallback(
    (dealId: string) =>
      updateDeal(dealId, (draft) => {
        const values = { ...draft.values }
        for (const field of template.fields) {
          if (field.aiFilled) values[field.id] = draft.aiValues[field.id] ?? ''
        }
        return {
          ...draft,
          values,
          evidence: draft.aiEvidence,
          sectionIssues: [],
          docKey: draft.docKey + 1,
          pendingAi: false,
          phase: 'ready',
        }
      }),
    [template, updateDeal],
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

  const generationFailed = useCallback(
    (dealId: string, reason: unknown) =>
      updateDeal(dealId, (draft) => ({
        ...draft,
        generationError: errorMessage(reason, '보고서를 저장하지 못했습니다.'),
        phase: isBlank(template, draft.values) ? 'idle' : 'ready',
      })),
    [template, updateDeal],
  )

  /** 보고서 작성과 미팅분석을 같은 report_id로 병렬 실행합니다. */
  const generate = useCallback(
    async (dealId: string, reportId: string, onStatus?: (status: AgentRunStatus) => void) => {
      const before = draftsByDeal[dealId] ?? stateOf(template, fallbackTitle)
      const wasBlank = !before.touched && isBlank(template, before.values)

      updateDeal(dealId, (draft) => ({
        ...draft,
        phase: 'generating',
        generationError: null,
        analysisPhase: 'running',
        analysisError: null,
      }))

      const writing = generateReportDraft(reportId, onStatus)
        .then((result) => {
          const generatedDraft: GeneratedDealDraft = {
            values: mergeGeneratedValues(template.fields, before.values, result.values, wasBlank),
            evidence: wasBlank ? result.evidence : before.evidence,
            aiValues: result.values,
            aiEvidence: result.evidence,
            aiGeneratedAt: new Date().toISOString(),
          }
          updateDeal(dealId, (draft) => {
            if (!wasBlank) {
              return {
                ...draft,
                phase: 'ready',
                aiValues: generatedDraft.aiValues,
                aiEvidence: generatedDraft.aiEvidence,
                aiGeneratedAt: generatedDraft.aiGeneratedAt,
                pendingAi: true,
              }
            }

            return {
              ...draft,
              phase: 'ready',
              values: generatedDraft.values,
              evidence: generatedDraft.evidence,
              aiValues: generatedDraft.aiValues,
              aiEvidence: generatedDraft.aiEvidence,
              aiGeneratedAt: generatedDraft.aiGeneratedAt,
              pendingAi: false,
              docKey: draft.docKey + 1,
            }
          })
          return generatedDraft
        })
        .catch((reason: unknown) => {
          updateDeal(dealId, (draft) => ({
            ...draft,
            phase: wasBlank ? 'idle' : 'ready',
            generationError: errorMessage(reason, '업무 보고서를 만들지 못했습니다.'),
          }))
          return null
        })

      const analysis = analyzeMeetingReport(reportId)
        .then((assessment) => {
          updateDeal(dealId, (draft) => ({
            ...draft,
            analysisPhase: 'completed',
            assessment,
          }))
        })
        .catch((reason: unknown) => {
          updateDeal(dealId, (draft) => ({
            ...draft,
            analysisPhase: 'failed',
            analysisError: errorMessage(reason, '미팅분석을 완료하지 못했습니다.'),
          }))
        })

      const [generatedDraft] = await Promise.all([writing, analysis])
      return generatedDraft
    },
    [draftsByDeal, template, fallbackTitle, updateDeal],
  )

  const hasSource = transcript.trim().length > 0 || files.attachments.length > 0

  return {
    template,
    transcript,
    setTranscript,
    attachments: files.attachments,
    addAttachments: files.addAttachments,
    removeAttachment: files.removeAttachment,
    attachmentError: files.attachmentError,
    salesDealIds,
    toggleSalesDeal,
    draftsByDeal,
    setTitle,
    applyDocument,
    restoreSections,
    startManual,
    applyAi,
    bindReport,
    generationFailed,
    generate,
    canGenerate:
      hasSource &&
      salesDealIds.length > 0 &&
      !files.attachments.some((attachment) => attachment.state === 'analyzing'),
    reset,
  }
}
