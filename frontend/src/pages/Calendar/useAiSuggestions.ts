import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  applyDateOnlySuggestion,
  getNextMeetingGenerationStatus,
  listNextMeetingSuggestions,
  refreshNextMeetingSuggestions,
  rejectNextMeetingSuggestion,
} from '@/api/contractAgent'
import { errorMessage } from '@/api/errorMessage'
import { RISK_LABEL } from '@/shared/riskLabels'
import type {
  AgendaItem,
  AiSuggestion,
  CalendarEvent,
  ContractNextMeetingSuggestion,
} from '@/types'

type Duration = 30 | 60 | 90
type NewEvent = Partial<Omit<CalendarEvent, 'id'>> & { date: string; title: string }
type AddEvent = (draft: NewEvent) => Promise<AgendaItem>

function durationLabel(minutes: Duration): string {
  if (minutes === 30) return '30분'
  if (minutes === 60) return '1시간'
  return '1시간 30분'
}

function toAiSuggestion(
  item: ContractNextMeetingSuggestion,
  duration: Duration | undefined,
): AiSuggestion {
  return {
    id: item.sales_deal_id,
    customerCompanyId: item.customer_company_id,
    customerContactId: item.customer_contact_id,
    owner: item.owner_display_name,
    hospital: item.customer_company_name,
    title: item.sales_deal_title,
    contact: item.customer_contact_name ?? '',
    dept: '',
    kind: 'visit',
    date: item.target_date,
    time: item.target_time?.slice(0, 5) ?? null,
    selectedDurationMinutes: duration ?? null,
    durationOptions: item.duration_options,
    place: '',
    activityTitle: `${item.sales_deal_title} 후속 미팅`,
    proposalReason: item.reason,
    basis: [...new Set(item.risks.map((risk) => RISK_LABEL[risk.code]))],
    scheduleRunId: item.schedule_management_run_id,
    refreshReason: item.refresh_reason,
  }
}

/** 캘린더의 한 날짜짜리 AI 추천 카드와 사용자 선택을 관리한다. */
export default function useAiSuggestions(addEvent: AddEvent) {
  const [items, setItems] = useState<ContractNextMeetingSuggestion[]>([])
  const [durations, setDurations] = useState<Record<string, Duration>>({})
  const [generating, setGenerating] = useState(false)
  const [latestReportPending, setLatestReportPending] = useState(false)
  const wasGenerating = useRef(false)
  const [previewId, setPreviewId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const suggestions = useMemo(
    () => items.map((item) => toAiSuggestion(item, durations[item.sales_deal_id])),
    [durations, items],
  )

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // 갱신 실패가 기존 카드를 지우면 안 된다. 조회는 별도로 끝까지 시도한다.
      await refreshNextMeetingSuggestions().catch(() => undefined)
      const [nextItems, status] = await Promise.all([
        listNextMeetingSuggestions(),
        getNextMeetingGenerationStatus(),
      ])
      setItems(nextItems)
      setGenerating(status.generating)
      setLatestReportPending(status.latest_report_pending)
      wasGenerating.current = status.generating
      setDurations({})
    } catch (cause) {
      setError(errorMessage(cause, 'AI 추천을 불러오지 못했습니다.'))
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const poll = async () => {
      try {
        const status = await getNextMeetingGenerationStatus()
        if (cancelled) return
        const finished = wasGenerating.current && !status.generating
        wasGenerating.current = status.generating
        setGenerating(status.generating)
        setLatestReportPending(status.latest_report_pending)
        if (finished) setItems(await listNextMeetingSuggestions())
      } catch {
        // 상태 조회 한 번의 실패로 기존 카드와 오류 영역을 지우지 않는다.
      }
    }
    const timer = window.setInterval(() => void poll(), 3000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  const selectDuration = useCallback((suggestionId: string, duration: Duration) => {
    setDurations((current) => ({ ...current, [suggestionId]: duration }))
  }, [])

  const accept = useCallback(
    async (suggestion: AiSuggestion, overrideDateISO?: string): Promise<AgendaItem | null> => {
      const duration = suggestion.selectedDurationMinutes
      if (duration === null) throw new Error('recommendation_duration_required')
      const targetDate = overrideDateISO ?? suggestion.date
      if (suggestion.time === null || suggestion.time === '') {
        await applyDateOnlySuggestion(suggestion.id, duration, targetDate)
        setItems((list) => list.filter((item) => item.sales_deal_id !== suggestion.id))
        return null
      }
      const added = await addEvent({
        date: targetDate,
        time: suggestion.time,
        dur: durationLabel(duration),
        kind: suggestion.kind,
        title: suggestion.activityTitle,
        hospital: suggestion.hospital,
        dept: suggestion.dept,
        contact: suggestion.contact,
        place: suggestion.place,
        salesDealId: suggestion.id,
        customerContactId: suggestion.customerContactId,
        scheduleManagementRunId: suggestion.scheduleRunId,
      })
      setItems((list) => list.filter((item) => item.sales_deal_id !== suggestion.id))
      return added
    },
    [addEvent],
  )

  const reject = useCallback(async (id: string) => {
    setError(null)
    try {
      await rejectNextMeetingSuggestion(id)
      // 서버는 거절 직후 계약관리 에이전트를 영속 큐에 넣는다. 상태 조회가 반영되기 전에도
      // 카드만 사라진 빈 화면으로 보이지 않도록 즉시 생성 중 상태를 표시한다.
      setGenerating(true)
      wasGenerating.current = true
      setLatestReportPending(false)
      setItems((list) => list.filter((item) => item.sales_deal_id !== id))
      setDurations((current) => {
        const next = { ...current }
        delete next[id]
        return next
      })
    } catch (cause) {
      setError(errorMessage(cause, '새 추천 날짜를 만들지 못했습니다.'))
    }
  }, [])

  return {
    suggestions,
    previewId,
    setPreviewId,
    loading,
    error,
    reload,
    generating,
    latestReportPending,
    selectDuration,
    accept,
    reject,
  }
}
