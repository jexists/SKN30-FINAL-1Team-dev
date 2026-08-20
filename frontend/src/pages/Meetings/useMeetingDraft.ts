// 미팅보고서 작성 화면의 상태를 전부 담습니다. 화면은 배치만 하고 규칙은 여기 있습니다.
//
// 구조화 결과는 임시저장된 보고서를 백엔드 agent-runs API에 전달해 받습니다.
import { useCallback, useEffect, useMemo, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import { generateReportDraft } from '@/api/reportAgent'
import { meetingTemplate } from '@/shared/meetings'
import type { AgendaItem, MeetingReport, ReportAttachment, ReportTemplate } from '@/types'

export type MeetingPhase = 'idle' | 'generating' | 'ready'

const emptyValues = (template: ReportTemplate) =>
  Object.fromEntries(template.fields.map((field) => [field.id, '']))

/**
 * @param item   기록할 일정. 값이 없으면 화면이 안내만 띄웁니다.
 * @param saved  이미 확정한 기록. 있으면 그 내용으로 시작해 고쳐 쓰게 합니다.
 */
export default function useMeetingDraft(item?: AgendaItem, saved?: MeetingReport) {
  const template = saved?.template ?? meetingTemplate

  const [phase, setPhase] = useState<MeetingPhase>('idle')
  const [transcript, setTranscript] = useState('')
  const [attachments, setAttachments] = useState<ReportAttachment[]>([])
  const [values, setValues] = useState<Record<string, string>>(() => emptyValues(template))
  const [aiFilledIds, setAiFilledIds] = useState<ReadonlySet<string>>(new Set())
  const [dirtyIds, setDirtyIds] = useState<ReadonlySet<string>>(new Set())
  const [evidence, setEvidence] = useState<string | undefined>(undefined)
  const [generationError, setGenerationError] = useState<string | null>(null)

  // 이미 쓴 기록이 있으면 그것으로, 없으면 빈 화면으로 시작합니다.
  const reset = useCallback(() => {
    setTranscript(saved?.transcript ?? '')
    setAttachments(saved?.attachments ?? [])
    setValues(saved ? { ...emptyValues(template), ...saved.values } : emptyValues(template))
    setAiFilledIds(new Set())
    setDirtyIds(new Set())
    setEvidence(saved?.evidence)
    setGenerationError(null)
    setPhase(saved ? 'ready' : 'idle')
  }, [saved, template])

  useEffect(() => {
    reset()
  }, [reset])

  const setValue = useCallback((id: string, value: string) => {
    setValues((prev) => ({ ...prev, [id]: value }))
    setDirtyIds((prev) => new Set(prev).add(id))
  }, [])

  /** 들은 것이 있어야 정리할 수 있습니다. 녹취든 메모든 하나는 있어야 합니다. */
  const canGenerate = transcript.trim().length > 0

  const generate = useCallback(
    async (reportId: string) => {
      if (!canGenerate || !item) return
      setPhase('generating')
      setGenerationError(null)

      try {
        const result = await generateReportDraft(reportId)
        const drafted = result.values
        // 사람이 손댄 항목은 덮지 않습니다. 덮어도 되는지는 화면이 먼저 묻습니다.
        setValues((prev) => {
          const next = { ...prev }
          for (const field of template.fields) {
            if (!field.aiFilled) continue
            if (dirtyIds.has(field.id)) continue
            next[field.id] = drafted[field.id] ?? ''
          }
          return next
        })
        setAiFilledIds(
          new Set(
            template.fields
              .filter((f) => f.aiFilled && !dirtyIds.has(f.id) && drafted[f.id])
              .map((f) => f.id),
          ),
        )
        setEvidence(result.evidence)
        setPhase('ready')
      } catch (reason: unknown) {
        setGenerationError(errorMessage(reason, '미팅 기록을 구조화하지 못했습니다.'))
        setPhase('ready')
      }
    },
    [canGenerate, item, dirtyIds, template],
  )

  /** 확정을 막는 이유들. 버튼 비활성과 안내 문구가 같은 값을 씁니다. */
  const missing = useMemo(() => {
    const reasons: string[] = []
    for (const field of template.fields) {
      if (field.required && !values[field.id]?.trim()) reasons.push(field.label)
    }
    return reasons
  }, [values, template])

  return {
    phase,
    template,
    transcript,
    setTranscript,
    attachments,
    values,
    setValue,
    aiFilledIds,
    dirtyIds,
    evidence,
    canGenerate,
    generate,
    generationError,
    missing,
    reset,
  }
}
