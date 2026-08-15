// 미팅보고서 작성 화면의 상태를 전부 담습니다. 화면은 배치만 하고 규칙은 여기 있습니다.
//
// AI 구조화는 generate() 안에서만 일어납니다. 나중에 이 함수 본문 하나를
// api/client.ts 호출로 바꾸면 화면은 그대로 둘 수 있습니다.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { meetingTemplate } from '@/shared/meetings'
import type { AgendaItem, MeetingReport, ReportAttachment } from '@/types'
import { fakeExtract, kindOf, sizeLabel } from '@/utils/attachment'

export type MeetingPhase = 'idle' | 'generating' | 'ready'

/** 구조화와 첨부 분석에 거는 흉내용 지연입니다. */
const GENERATE_MS = 900
const ANALYZE_MS = 1400

const emptyValues = () => Object.fromEntries(meetingTemplate.fields.map((f) => [f.id, '']))

/**
 * @param item   기록할 일정. 값이 없으면 화면이 안내만 띄웁니다.
 * @param saved  이미 확정한 기록. 있으면 그 내용으로 시작해 고쳐 쓰게 합니다.
 */
export default function useMeetingDraft(item?: AgendaItem, saved?: MeetingReport) {
  const template = meetingTemplate

  const [phase, setPhase] = useState<MeetingPhase>('idle')
  const [transcript, setTranscript] = useState('')
  const [attachments, setAttachments] = useState<ReportAttachment[]>([])
  const [values, setValues] = useState<Record<string, string>>(emptyValues)
  const [aiFilledIds, setAiFilledIds] = useState<ReadonlySet<string>>(new Set())
  const [dirtyIds, setDirtyIds] = useState<ReadonlySet<string>>(new Set())
  const [evidence, setEvidence] = useState<string | undefined>(undefined)
  /** 마지막 구조화 이후 분석이 끝난 첨부가 있는지. "다시 구조화" 안내를 띄웁니다. */
  const [staleAttachments, setStaleAttachments] = useState(false)

  // 지연 타이머가 살아 있는 동안 화면을 떠나면 없는 상태를 건드리게 됩니다.
  const timers = useRef<ReturnType<typeof setTimeout>[]>([])
  useEffect(() => {
    const pending = timers.current
    return () => pending.forEach(clearTimeout)
  }, [])

  const later = useCallback((fn: () => void, ms: number) => {
    timers.current.push(setTimeout(fn, ms))
  }, [])

  // 이미 쓴 기록이 있으면 그것으로, 없으면 빈 화면으로 시작합니다.
  const reset = useCallback(() => {
    setTranscript(saved?.transcript ?? '')
    setAttachments(saved?.attachments ?? [])
    setValues(saved ? { ...emptyValues(), ...saved.values } : emptyValues())
    setAiFilledIds(new Set())
    setDirtyIds(new Set())
    setEvidence(saved?.evidence)
    setStaleAttachments(false)
    setPhase(saved ? 'ready' : 'idle')
  }, [saved])

  useEffect(() => {
    reset()
  }, [reset])

  const attach = useCallback(
    (files: FileList | File[]) => {
      const added: ReportAttachment[] = Array.from(files).map((file, index) => ({
        id: `matt-${Date.now()}-${index}`,
        kind: kindOf(file),
        name: file.name,
        size: sizeLabel(file.size),
        state: 'analyzing',
      }))
      if (added.length === 0) return
      setAttachments((prev) => [...prev, ...added])

      // 분석이 끝나야 구조화에 쓸 수 있습니다. 그동안에도 버튼은 막지 않습니다.
      added.forEach((file) => {
        later(() => {
          setAttachments((prev) =>
            prev.map((a) =>
              a.id === file.id ? { ...a, state: 'done', extract: fakeExtract(a.kind, a.name) } : a,
            ),
          )
          setStaleAttachments(true)
        }, ANALYZE_MS)
      })
    },
    [later],
  )

  const removeAttachment = useCallback((id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id))
  }, [])

  const setValue = useCallback((id: string, value: string) => {
    setValues((prev) => ({ ...prev, [id]: value }))
    setDirtyIds((prev) => new Set(prev).add(id))
  }, [])

  const analyzing = attachments.filter((a) => a.state === 'analyzing').length
  const ready = useMemo(() => attachments.filter((a) => a.state === 'done'), [attachments])

  /** 들은 것이 있어야 정리할 수 있습니다. 녹취든 메모든 하나는 있어야 합니다. */
  const canGenerate = transcript.trim().length > 0 || ready.length > 0

  const generate = useCallback(() => {
    if (!canGenerate || !item) return
    setPhase('generating')

    later(() => {
      const lines = transcript
        .split(/[.\n]/)
        .map((line) => line.trim())
        .filter(Boolean)
      const fromFiles = ready.map((a) => `· ${a.extract}`).join('\n')

      const drafted: Record<string, string> = {
        attendees: item.contact,
        reaction: lines.slice(0, 2).join('\n') || fromFiles,
        decision: lines.slice(2).join('\n') || fromFiles,
        next: `${item.product} 관련 요청 자료를 정리해 ${item.contact}에게 회신합니다.`,
      }

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
      setEvidence(
        ready.length > 0
          ? `직접 입력 ${lines.length}문장과 첨부 ${ready.length}건에서 정리했습니다. 확인되지 않은 내용은 비워 두었습니다.`
          : `직접 입력 ${lines.length}문장에서 정리했습니다. 첨부가 없어 확인되지 않은 내용은 비워 두었습니다.`,
      )
      setStaleAttachments(false)
      setPhase('ready')
    }, GENERATE_MS)
  }, [canGenerate, item, transcript, ready, dirtyIds, later, template])

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
    analyzingCount: analyzing,
    staleAttachments,
    attach,
    removeAttachment,
    values,
    setValue,
    aiFilledIds,
    dirtyIds,
    evidence,
    canGenerate,
    generate,
    missing,
    reset,
  }
}
