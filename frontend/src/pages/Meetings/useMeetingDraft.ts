// 업무보고서 작성 화면의 상태를 전부 담습니다. 화면은 배치만 하고 규칙은 여기 있습니다.
//
// 이 파일의 핵심은 두 벌을 따로 두는 것입니다.
//
//   aiValues  — AI 가 최초로 만든 원본. 화면에서 읽기만 합니다.
//   values    — 사람이 고치는 최종 보고서. 저장 대상입니다.
//
// 한 벌로 관리하면 사용자가 한 글자만 고쳐도 AI 가 뭐라고 썼는지 되짚을 수 없습니다.
// 그래서 generate() 는 aiValues 에만 쓰고, values 로 옮기는 것은 applyAi() 뿐입니다.
import { useCallback, useEffect, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import { generateReportDraft } from '@/api/reportAgent'
import { meetingTemplate } from '@/shared/meetings'
import useAttachments from '@/shared/useAttachments'
import type { AgendaItem, AgentRunStatus, MeetingReport, ReportTemplate } from '@/types'

export type MeetingPhase = 'idle' | 'generating' | 'ready'

const emptyValues = (template: ReportTemplate) =>
  Object.fromEntries(template.fields.map((field) => [field.id, '']))

const isBlank = (template: ReportTemplate, values: Record<string, string>) =>
  template.fields.every((field) => !values[field.id]?.trim())

/**
 * @param item   기록할 일정. 값이 없으면 화면이 안내만 띄웁니다.
 * @param saved  이미 쓰기 시작한 기록. 있으면 그 내용으로 시작해 고쳐 쓰게 합니다.
 */
export default function useMeetingDraft(item?: AgendaItem, saved?: MeetingReport) {
  const template = saved?.template ?? meetingTemplate

  const [phase, setPhase] = useState<MeetingPhase>('idle')
  const [title, setTitle] = useState('')
  const [transcript, setTranscript] = useState('')
  // 음성에서 뽑은 글은 사람이 쓴 것을 덮지 않습니다. 있으면 아래에 붙입니다.
  const files = useAttachments((text) =>
    setTranscript((prev) => (prev.trim() ? `${prev.trim()}\n\n${text}` : text)),
  )
  /** 이 미팅이 어느 영업 현황에 대한 것인지. 여러 건일 수 있습니다. */
  const [salesDealIds, setSalesDealIds] = useState<string[]>([])

  // 최종 보고서 — 저장되는 값입니다. 화면에서는 문서 한 편으로 보이지만 저장되는
  // 모양은 그대로 항목별 값입니다. 오가는 변환은 reportDocument.ts 가 맡습니다.
  const [values, setValues] = useState<Record<string, string>>(() => emptyValues(template))
  const [evidence, setEvidence] = useState<string | undefined>(undefined)
  /** 사람이 문서를 건드린 적이 있는가. 항목 단위로는 알 수 없어 한 덩어리로 봅니다. */
  const [touched, setTouched] = useState(false)
  /**
   * 편집기를 다시 세워야 할 때 올립니다.
   *
   * TinyMCE 는 비제어로 둡니다 — 글자를 칠 때마다 값을 되먹이면 한글 조합이 끊기고
   * 커서가 튑니다. 그래서 문서를 통째로 갈아야 할 때만 이 값을 올려 다시 마운트합니다.
   */
  const [docKey, setDocKey] = useState(0)
  /** 문서에서 사라진 항목 제목. 있으면 저장을 막습니다. */
  const [sectionIssues, setSectionIssues] = useState<string[]>([])

  // AI 원본 — 여기서 만들고 여기서만 바뀝니다.
  const [aiValues, setAiValues] = useState<Record<string, string>>({})
  const [aiEvidence, setAiEvidence] = useState<string | undefined>(undefined)
  const [aiGeneratedAt, setAiGeneratedAt] = useState<string | undefined>(undefined)
  /** 최종 보고서에 아직 옮기지 않은 새 원본이 있는가. */
  const [pendingAi, setPendingAi] = useState(false)

  const [generationError, setGenerationError] = useState<string | null>(null)

  const { setAttachments, setAttachmentError } = files

  // 이미 쓴 기록이 있으면 그것으로, 없으면 빈 화면으로 시작합니다.
  const reset = useCallback(() => {
    const next = saved ? { ...emptyValues(template), ...saved.values } : emptyValues(template)
    setTitle(saved?.title ?? item?.title ?? '')
    setTranscript(saved?.transcript ?? '')
    setAttachments(saved?.attachments ?? [])
    // 쓰던 것이 있으면 그대로, 아니면 일정에 이미 걸린 딜 한 건을 미리 골라 둡니다.
    // 대개 그 딜에 대한 미팅이라 매번 같은 것을 다시 고르게 할 이유가 없습니다.
    setSalesDealIds(saved?.salesDealIds ?? (item?.salesDealId ? [item.salesDealId] : []))
    setValues(next)
    setTouched(false)
    setSectionIssues([])
    setDocKey((key) => key + 1)
    setEvidence(saved?.evidence)
    setAiValues(saved?.aiValues ?? {})
    setAiEvidence(saved?.aiEvidence)
    setAiGeneratedAt(saved?.aiGeneratedAt)
    setPendingAi(false)
    setGenerationError(null)
    setAttachmentError(null)
    // 빈 폼을 펼쳐 두지 않습니다. 쓸 것이 있을 때만 편집 화면이 열립니다.
    setPhase(isBlank(template, next) ? 'idle' : 'ready')
    // item 전체가 아니라 여기서 실제로 읽는 값만 봅니다. 일정 목록이 다시 그려질 때마다
    // 객체가 새로 오면 reset 이 새로 만들어져 effect 가 끝없이 돕니다.
  }, [saved, item?.title, item?.salesDealId, template, setAttachments, setAttachmentError])

  useEffect(() => {
    reset()
  }, [reset])

  /**
   * 편집기가 돌려준 문서를 항목별 값으로 받습니다.
   *
   * @param missing 문서에서 사라진 항목 제목. 저장을 막는 근거가 됩니다.
   */
  const applyDocument = useCallback((next: Record<string, string>, missing: string[]) => {
    setValues(next)
    setSectionIssues(missing)
    setTouched(true)
  }, [])

  /** 사라진 항목 제목을 되살립니다. 편집기를 지금 값으로 다시 세우면 제목이 돌아옵니다. */
  const restoreSections = useCallback(() => {
    setSectionIssues([])
    setDocKey((key) => key + 1)
  }, [])

  /** AI 없이 직접 쓰겠다고 고른 경우. 빈 폼을 펼칩니다. */
  const startManual = useCallback(() => setPhase('ready'), [])

  const toggleSalesDeal = useCallback((id: string) => {
    setSalesDealIds((prev) =>
      prev.includes(id) ? prev.filter((one) => one !== id) : [...prev, id],
    )
  }, [])

  /**
   * AI 원본을 최종 보고서로 옮깁니다. 원본을 그대로 베끼므로 부분 병합이 아닙니다.
   * 사람이 고친 값을 지우는 일이라 부르는 쪽이 먼저 묻습니다.
   */
  const applyAi = useCallback(() => {
    setValues((prev) => {
      const next = { ...prev }
      for (const field of template.fields) {
        if (!field.aiFilled) continue
        next[field.id] = aiValues[field.id] ?? ''
      }
      return next
    })
    setEvidence(aiEvidence)
    setSectionIssues([])
    setDocKey((key) => key + 1)
    setPendingAi(false)
    setPhase('ready')
  }, [aiValues, aiEvidence, template])

  /** 들은 것이 있어야 정리할 수 있습니다. 적은 내용이든 첨부든 하나는 있어야 합니다. */
  const canGenerate = transcript.trim().length > 0 || files.attachments.length > 0

  /** @returns 원본을 만들었는지. 부르는 쪽이 성공했을 때만 화면을 옮기게 합니다. */
  const generate = useCallback(
    async (reportId: string, onStatus?: (status: AgentRunStatus) => void) => {
      if (!canGenerate || !item) return false
      const wasBlank = !touched && isBlank(template, values)
      setPhase('generating')
      setGenerationError(null)

      try {
        const result = await generateReportDraft(reportId, onStatus)
        setAiValues(result.values)
        setAiEvidence(result.evidence)
        setAiGeneratedAt(new Date().toISOString())

        if (wasBlank) {
          // 처음 한 번은 바로 최종 보고서로 옮깁니다. 백지에 대고 "적용할까요" 를
          // 묻는 것은 되물을 것이 없는 질문입니다.
          setValues((prev) => {
            const next = { ...prev }
            for (const field of template.fields) {
              if (!field.aiFilled) continue
              next[field.id] = result.values[field.id] ?? ''
            }
            return next
          })
          setEvidence(result.evidence)
          setPendingAi(false)
          setDocKey((key) => key + 1)
          setPhase('ready')
          return true
        }

        // 이미 쓴 것이 있으면 최종 보고서를 건드리지 않습니다. 옮길지는 사람이 정합니다.
        setPendingAi(true)
        setPhase('ready')
        return true
      } catch (reason: unknown) {
        setGenerationError(errorMessage(reason, '업무 보고서를 만들지 못했습니다.'))
        // 실패했는데 편집 화면을 펼치면 빈 폼만 남습니다. 있던 자리로 돌립니다.
        setPhase(wasBlank ? 'idle' : 'ready')
        return false
      }
    },
    [canGenerate, item, touched, template, values],
  )

  return {
    phase,
    template,
    title,
    setTitle,
    transcript,
    setTranscript,
    attachments: files.attachments,
    addAttachments: files.addAttachments,
    removeAttachment: files.removeAttachment,
    attachmentError: files.attachmentError,
    salesDealIds,
    toggleSalesDeal,
    values,
    applyDocument,
    restoreSections,
    sectionIssues,
    docKey,
    evidence,
    aiValues,
    aiEvidence,
    aiGeneratedAt,
    hasAiOriginal: Object.keys(aiValues).length > 0,
    pendingAi,
    applyAi,
    canGenerate,
    generate,
    generationError,
    startManual,
    reset,
  }
}
