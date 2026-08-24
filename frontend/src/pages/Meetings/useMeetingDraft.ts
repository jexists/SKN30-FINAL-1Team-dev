// 미팅보고서 작성 화면의 상태를 전부 담습니다. 화면은 배치만 하고 규칙은 여기 있습니다.
//
// 이 파일의 핵심은 두 벌을 따로 두는 것입니다.
//
//   aiValues  — AI 가 최초로 만든 원본. 화면에서 읽기만 합니다.
//   values    — 사람이 고치는 최종 보고서. 저장 대상입니다.
//
// 한 벌로 관리하면 사용자가 한 글자만 고쳐도 AI 가 뭐라고 썼는지 되짚을 수 없습니다.
// 그래서 generate() 는 aiValues 에만 쓰고, values 로 옮기는 것은 applyAi() 뿐입니다.
import { useCallback, useEffect, useMemo, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import { generateReportDraft } from '@/api/reportAgent'
import { meetingTemplate } from '@/shared/meetings'
import type { AgendaItem, MeetingReport, ReportAttachment, ReportTemplate } from '@/types'

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
  const [attachments, setAttachments] = useState<ReportAttachment[]>([])

  // 최종 보고서 — 저장되는 값입니다.
  const [values, setValues] = useState<Record<string, string>>(() => emptyValues(template))
  const [dirtyIds, setDirtyIds] = useState<ReadonlySet<string>>(new Set())
  const [evidence, setEvidence] = useState<string | undefined>(undefined)

  // AI 원본 — 여기서 만들고 여기서만 바뀝니다.
  const [aiValues, setAiValues] = useState<Record<string, string>>({})
  const [aiEvidence, setAiEvidence] = useState<string | undefined>(undefined)
  const [aiGeneratedAt, setAiGeneratedAt] = useState<string | undefined>(undefined)
  /** 최종 보고서에 아직 옮기지 않은 새 원본이 있는가. */
  const [pendingAi, setPendingAi] = useState(false)

  const [generationError, setGenerationError] = useState<string | null>(null)

  // 이미 쓴 기록이 있으면 그것으로, 없으면 빈 화면으로 시작합니다.
  const reset = useCallback(() => {
    const next = saved ? { ...emptyValues(template), ...saved.values } : emptyValues(template)
    setTitle(saved?.title ?? item?.title ?? '')
    setTranscript(saved?.transcript ?? '')
    setAttachments(saved?.attachments ?? [])
    setValues(next)
    setDirtyIds(new Set())
    setEvidence(saved?.evidence)
    setAiValues(saved?.aiValues ?? {})
    setAiEvidence(saved?.aiEvidence)
    setAiGeneratedAt(saved?.aiGeneratedAt)
    setPendingAi(false)
    setGenerationError(null)
    // 빈 폼을 펼쳐 두지 않습니다. 쓸 것이 있을 때만 편집 화면이 열립니다.
    setPhase(isBlank(template, next) ? 'idle' : 'ready')
    // item 전체가 아니라 여기서 실제로 읽는 값만 봅니다. 일정 목록이 다시 그려질 때마다
    // 객체가 새로 오면 reset 이 새로 만들어져 effect 가 끝없이 돕니다.
  }, [saved, item?.title, template])

  useEffect(() => {
    reset()
  }, [reset])

  const setValue = useCallback((id: string, value: string) => {
    setValues((prev) => ({ ...prev, [id]: value }))
    setDirtyIds((prev) => new Set(prev).add(id))
  }, [])

  /** AI 없이 직접 쓰겠다고 고른 경우. 빈 폼을 펼칩니다. */
  const startManual = useCallback(() => setPhase('ready'), [])

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
    setDirtyIds(new Set())
    setEvidence(aiEvidence)
    setPendingAi(false)
    setPhase('ready')
  }, [aiValues, aiEvidence, template])

  /** 들은 것이 있어야 정리할 수 있습니다. 녹취든 메모든 하나는 있어야 합니다. */
  const canGenerate = transcript.trim().length > 0

  const generate = useCallback(
    async (reportId: string) => {
      if (!canGenerate || !item) return
      const wasBlank = dirtyIds.size === 0 && isBlank(template, values)
      setPhase('generating')
      setGenerationError(null)

      try {
        const result = await generateReportDraft(reportId)
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
          setPhase('ready')
          return
        }

        // 이미 쓴 것이 있으면 최종 보고서를 건드리지 않습니다. 옮길지는 사람이 정합니다.
        setPendingAi(true)
        setPhase('ready')
      } catch (reason: unknown) {
        setGenerationError(errorMessage(reason, '미팅 보고서를 만들지 못했습니다.'))
        // 실패했는데 편집 화면을 펼치면 빈 폼만 남습니다. 있던 자리로 돌립니다.
        setPhase(wasBlank ? 'idle' : 'ready')
      }
    },
    [canGenerate, item, dirtyIds, template, values],
  )

  /**
   * AI 가 쓴 그대로인 항목. 저장할 때마다 다시 그려지는 화면이라 따로 들고 있으면
   * 새로고침 한 번에 사라집니다. 두 벌을 맞대어 그때그때 셉니다. 사람이 손대는 순간
   * 값이 갈리므로 배지도 같이 사라집니다 — 그것이 이 배지가 뜻하는 바입니다.
   */
  const aiFilledIds = useMemo(() => {
    const ids = new Set<string>()
    for (const field of template.fields) {
      const original = aiValues[field.id]?.trim()
      if (original && values[field.id]?.trim() === original) ids.add(field.id)
    }
    return ids as ReadonlySet<string>
  }, [aiValues, values, template])

  /** 확정을 막는 이유들. 버튼 비활성과 안내 문구가 같은 값을 씁니다. */
  const missing = useMemo(() => {
    const reasons: string[] = []
    if (!title.trim()) reasons.push('보고서 제목')
    for (const field of template.fields) {
      if (field.required && !values[field.id]?.trim()) reasons.push(field.label)
    }
    return reasons
  }, [title, values, template])

  return {
    phase,
    template,
    title,
    setTitle,
    transcript,
    setTranscript,
    attachments,
    values,
    setValue,
    aiFilledIds,
    dirtyIds,
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
    missing,
    reset,
  }
}
