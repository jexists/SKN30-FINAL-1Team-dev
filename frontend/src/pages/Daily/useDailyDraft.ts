// 작성 화면의 상태를 전부 담습니다. 화면은 배치만 하고 규칙은 여기 있습니다.
//
// AI 초안은 generate() 안에서만 만들어집니다. 나중에 이 함수 본문 하나를
// api/client.ts 호출로 바꾸면 화면은 그대로 둘 수 있습니다.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { meetingActivitiesFor } from '@/shared/meetings'
import { draftActivitiesFor, templateFor } from '@/shared/reports'
import type { ReportActivity, ReportAttachment, ReportKind, ReportTemplate } from '@/types'
import useMeetingReports from '@/pages/Meetings/useMeetingReports'
import { fakeExtract, kindOf, sizeLabel } from '@/utils/attachment'

export type DraftPhase = 'idle' | 'generating' | 'ready' | 'submitted'

/** 초안 생성과 첨부 분석에 거는 흉내용 지연입니다. */
const GENERATE_MS = 900
const ANALYZE_MS = 1400

const emptyValues = (template: ReportTemplate) =>
  Object.fromEntries(template.fields.map((f) => [f.id, '']))

export default function useDailyDraft(dateISO: string, kind: ReportKind) {
  const template = templateFor(kind)

  // 그날 확정한 미팅 기록도 활동 후보입니다. reset() 이 이 배열을 의존성으로 쓰므로
  // 날짜가 그대로면 같은 배열이어야 다시 수집이 반복되지 않습니다.
  const { byDate } = useMeetingReports()
  const fromMeetings = useMemo(
    () => meetingActivitiesFor(byDate.get(dateISO) ?? []),
    [byDate, dateISO],
  )

  const [phase, setPhase] = useState<DraftPhase>('idle')
  const [activities, setActivities] = useState<ReportActivity[]>(() => draftActivitiesFor(dateISO))
  const [attachments, setAttachments] = useState<ReportAttachment[]>([])
  const [values, setValues] = useState<Record<string, string>>(() => emptyValues(template))
  const [aiFilledIds, setAiFilledIds] = useState<ReadonlySet<string>>(new Set())
  const [dirtyIds, setDirtyIds] = useState<ReadonlySet<string>>(new Set())
  /** 마지막 생성 이후 분석이 끝난 첨부가 있는지. "다시 작성" 안내를 띄웁니다. */
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

  // 날짜나 종류가 바뀌면 그날 일정으로 다시 수집하고 처음 상태로 돌아갑니다.
  // 쓰던 내용을 지워도 되는지는 화면이 먼저 묻습니다.
  const reset = useCallback(() => {
    setActivities([...draftActivitiesFor(dateISO), ...fromMeetings])
    setAttachments([])
    setValues(emptyValues(template))
    setAiFilledIds(new Set())
    setDirtyIds(new Set())
    setStaleAttachments(false)
    setPhase('idle')
  }, [dateISO, template, fromMeetings])

  useEffect(() => {
    reset()
  }, [reset])

  const toggleActivity = useCallback((id: string) => {
    setActivities((prev) => prev.map((a) => (a.id === id ? { ...a, included: !a.included } : a)))
  }, [])

  const addManual = useCallback((title: string) => {
    setActivities((prev) => [
      ...prev,
      {
        id: `manual-${Date.now()}`,
        source: '수기',
        title,
        desc: '직접 입력한 항목',
        included: true,
      },
    ])
  }, [])

  const removeActivity = useCallback((id: string) => {
    setActivities((prev) => prev.filter((a) => a.id !== id))
  }, [])

  const attach = useCallback(
    (files: FileList | File[]) => {
      const added: ReportAttachment[] = Array.from(files).map((file, index) => ({
        id: `att-${Date.now()}-${index}`,
        kind: kindOf(file),
        name: file.name,
        size: sizeLabel(file.size),
        state: 'analyzing',
      }))
      if (added.length === 0) return
      setAttachments((prev) => [...prev, ...added])

      // 분석이 끝나야 초안에 쓸 수 있습니다. 그동안에도 작성 버튼은 막지 않습니다.
      added.forEach((item) => {
        later(() => {
          setAttachments((prev) =>
            prev.map((a) =>
              a.id === item.id ? { ...a, state: 'done', extract: fakeExtract(a.kind, a.name) } : a,
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

  const included = useMemo(() => activities.filter((a) => a.included), [activities])
  const analyzing = attachments.filter((a) => a.state === 'analyzing').length
  const ready = attachments.filter((a) => a.state === 'done')

  /** AI 가 채우는 항목이 있는 양식에서만 초안 생성이 의미가 있습니다. */
  const hasAiFields = useMemo(() => template.fields.some((f) => f.aiFilled), [template])

  /** 캘린더 활동만 있으면 됩니다. 첨부는 조건이 아닙니다. */
  const canGenerate = hasAiFields && included.length > 0

  const generate = useCallback(() => {
    if (!canGenerate) return
    setPhase('generating')

    later(() => {
      const summary = included.map((a) => `· ${a.title}`).join('\n')
      const fromFiles = ready.map((a) => `· ${a.extract}`).join('\n')
      const issues = included.filter((a) => a.source === '후속').map((a) => `· ${a.desc}`)

      const drafted: Record<string, string> = {
        summary: fromFiles ? `${summary}\n${fromFiles}` : summary,
        issue: issues.join('\n'),
        next: '후속이 밀린 건의 방문 일정을 등록하고, 요청받은 자료를 회신합니다.',
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
      setStaleAttachments(false)
      setPhase('ready')
    }, GENERATE_MS)
  }, [canGenerate, included, ready, dirtyIds, later, template])

  /** 제출을 막는 이유들. 버튼 비활성과 안내 문구가 같은 값을 씁니다. */
  const missing = useMemo(() => {
    const reasons: string[] = []
    if (included.length === 0) reasons.push('활동 1건 이상')
    for (const field of template.fields) {
      if (field.required && !values[field.id]?.trim()) reasons.push(field.label)
    }
    return reasons
  }, [included, values, template])

  return {
    phase,
    setPhase,
    template,
    hasAiFields,
    activities,
    includedCount: included.length,
    toggleActivity,
    addManual,
    removeActivity,
    attachments,
    analyzingCount: analyzing,
    staleAttachments,
    attach,
    removeAttachment,
    values,
    setValue,
    aiFilledIds,
    dirtyIds,
    canGenerate,
    generate,
    missing,
    reset,
  }
}
