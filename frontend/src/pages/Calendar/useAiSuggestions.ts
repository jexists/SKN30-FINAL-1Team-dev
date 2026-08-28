import { useCallback, useState } from 'react'

import { dismissNextMeetingSuggestion, listNextMeetingSuggestions } from '@/api/contractAgent'
import { errorMessage } from '@/api/errorMessage'
import { durationLabel, kstParts } from '@/shared/agenda'
import { RISK_LABEL } from '@/shared/riskLabels'
import type {
  AgendaItem,
  AiSuggestion,
  CalendarEvent,
  ContractNextMeetingSuggestion,
  ScheduleCandidate,
} from '@/types'

type NewEvent = Partial<Omit<CalendarEvent, 'id'>> & { date: string; title: string }
type AddEvent = (draft: NewEvent) => Promise<AgendaItem>

/** priority 가 가장 작은(=가장 추천하는) 일정 후보를 고른다. */
function bestCandidate(candidates: ScheduleCandidate[]): ScheduleCandidate | null {
  return candidates.reduce<ScheduleCandidate | null>(
    (best, candidate) => (best === null || candidate.priority < best.priority ? candidate : best),
    null,
  )
}

function toAiSuggestion(item: ContractNextMeetingSuggestion): AiSuggestion | null {
  const best = bestCandidate(item.schedule_candidates)
  if (!best) return null
  const start = kstParts(best.starts_at)
  return {
    id: item.sales_deal_id,
    customerCompanyId: item.customer_company_id,
    customerContactId: item.customer_contact_id,
    owner: item.owner_display_name,
    hospital: item.customer_company_name,
    title: item.sales_deal_title,
    contact: item.customer_contact_name ?? '',
    dept: '',
    kind: best.activity_type === 'task' ? 'internal' : 'visit',
    date: start.date,
    time: start.time,
    dur: durationLabel(best.starts_at, best.ends_at),
    startsAt: best.starts_at,
    endsAt: best.ends_at,
    place: '',
    activityTitle: best.title,
    proposalReason: item.reason,
    basis: [...new Set(item.risks.map((risk) => RISK_LABEL[risk.code]))],
    scheduleRunId: item.schedule_management_run_id,
  }
}

/**
 * 캘린더 "AI 추천 일정" 패널의 데이터·동작을 소유한다.
 *
 * 트리거(보고서 승인·일정 수동 등록·영업 딜 생성/이동·CS 접수 처리 시작)가 서버에서 미리
 * 계산해 저장해 둔 제안을 조회만 한다 — LLM을 직접 호출하지 않으므로 화면이 바로 뜬다.
 * 자세한 배경은 docs/technical/multiagent/계약에이전트_설계.md 11장 참고.
 */
export default function useAiSuggestions(addEvent: AddEvent) {
  const [suggestions, setSuggestions] = useState<AiSuggestion[]>([])
  const [previewId, setPreviewId] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setRefreshing(true)
    setError(null)
    try {
      const items = await listNextMeetingSuggestions()
      const next = items.map(toAiSuggestion).filter((item): item is AiSuggestion => item !== null)
      setSuggestions(next)
    } catch (cause) {
      setError(errorMessage(cause, 'AI 추천을 불러오지 못했습니다.'))
      setSuggestions([])
    } finally {
      setRefreshing(false)
    }
  }, [])

  const accept = useCallback(
    async (suggestion: AiSuggestion, overrideDateISO?: string) => {
      const added = await addEvent({
        date: overrideDateISO ?? suggestion.date,
        time: suggestion.time,
        dur: suggestion.dur,
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
      setSuggestions((list) => list.filter((s) => s.id !== suggestion.id))
      return added
    },
    [addEvent],
  )

  const dismiss = useCallback((id: string) => {
    setSuggestions((list) => list.filter((s) => s.id !== id))
    // 서버 반영에 실패해도 화면은 이미 닫힌 채로 둔다 — 다음 refresh에서 다시 나타날 수 있다.
    void dismissNextMeetingSuggestion(id).catch(() => {})
  }, [])

  return {
    suggestions,
    previewId,
    setPreviewId,
    refreshing,
    error,
    refresh,
    accept,
    dismiss,
  }
}
