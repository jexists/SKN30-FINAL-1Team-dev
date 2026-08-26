import { useCallback, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import {
  proposeNextMeeting,
  scheduleCandidates,
  selectNextMeetingCandidates,
} from '@/api/contractAgent'
import { durationLabel, kstParts } from '@/shared/agenda'
import { RISK_LABEL } from '@/shared/riskLabels'
import type {
  AgendaItem,
  AiSuggestion,
  AiSuggestionReady,
  CalendarEvent,
  SalesDealResponse,
  ScheduleCandidate,
} from '@/types'

type NewEvent = Partial<Omit<CalendarEvent, 'id'>> & { date: string; title: string }
type AddEvent = (draft: NewEvent) => Promise<AgendaItem>

function pickBase(s: AiSuggestion) {
  const {
    id,
    customerCompanyId,
    customerContactId,
    owner,
    hospital,
    title,
    contact,
    dept,
    reason,
    priority,
  } = s
  return {
    id,
    customerCompanyId,
    customerContactId,
    owner,
    hospital,
    title,
    contact,
    dept,
    reason,
    priority,
  }
}

/** priority 가 가장 작은(=가장 추천하는) 일정 후보를 고른다. */
function bestCandidate(candidates: ScheduleCandidate[]): ScheduleCandidate | null {
  return candidates.reduce<ScheduleCandidate | null>(
    (best, candidate) => (best === null || candidate.priority < best.priority ? candidate : best),
    null,
  )
}

/**
 * 캘린더 "AI 추천 일정" 패널의 데이터·동작을 소유한다.
 *
 * LLM 호출을 아끼려고 2단계로 나눈다: `refresh`는 0차 선별 1회 호출로 후보 전체를
 * "접힌" 상태로 보여주고, `expand`는 사용자가 카드 하나를 펼칠 때만 그 건에 한해
 * 1차 제안 + 일정 후보를 이어서 호출한다. 자세한 배경은
 * docs/technical/multiagent/계약에이전트_설계.md 11장 참고.
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
      const { candidates } = await selectNextMeetingCandidates()
      const deals = await Promise.all(
        candidates.map((candidate) =>
          client
            .get<SalesDealResponse>(`/sales-deals/${candidate.sales_deal_id}`)
            .then(({ data }) => data)
            .catch(() => null),
        ),
      )
      const next = candidates
        .map((candidate, index): AiSuggestion | null => {
          const deal = deals[index]
          if (!deal) return null
          return {
            status: 'collapsed',
            id: candidate.sales_deal_id,
            customerCompanyId: candidate.customer_company_id,
            customerContactId: deal.customer_contact_id,
            owner: deal.owner_display_name,
            hospital: deal.customer_company_name,
            title: deal.title,
            contact: deal.customer_contact_name ?? '',
            dept: '',
            reason: candidate.reason,
            priority: candidate.priority,
          }
        })
        .filter((item): item is AiSuggestion => item !== null)
        .sort((a, b) => a.priority - b.priority)
      setSuggestions(next)
    } catch (cause) {
      setError(errorMessage(cause, 'AI 추천을 불러오지 못했습니다.'))
      setSuggestions([])
    } finally {
      setRefreshing(false)
    }
  }, [])

  const expand = useCallback(
    async (id: string) => {
      const target = suggestions.find((s) => s.id === id)
      if (!target || target.status === 'loading') return
      setSuggestions((list) =>
        list.map((s) => (s.id === id ? { ...pickBase(s), status: 'loading' } : s)),
      )

      try {
        const proposal = await proposeNextMeeting(target.customerCompanyId)
        const meeting = proposal.output.next_meeting_suggestion
        if (!meeting) throw new Error('지금은 다음 미팅이 필요하지 않다고 판단했습니다.')

        const schedule = await scheduleCandidates(meeting.sales_deal_id, proposal.runId)
        const best = bestCandidate(schedule.output.schedule_candidates)
        if (!best) throw new Error('겹치지 않는 일정 후보를 찾지 못했습니다.')

        const start = kstParts(best.starts_at)
        const ready: AiSuggestionReady = {
          ...pickBase(target),
          status: 'ready',
          kind: best.activity_type === 'task' ? 'internal' : 'visit',
          date: start.date,
          time: start.time,
          dur: durationLabel(best.starts_at, best.ends_at),
          startsAt: best.starts_at,
          endsAt: best.ends_at,
          place: '',
          activityTitle: best.title,
          proposalReason: meeting.reason,
          basis: [...new Set(proposal.output.risks.map((risk) => RISK_LABEL[risk.code]))],
          scheduleRunId: schedule.runId,
        }
        setSuggestions((list) => list.map((s) => (s.id === id ? ready : s)))
      } catch (cause) {
        setSuggestions((list) =>
          list.map((s) =>
            s.id === id
              ? {
                  ...pickBase(s),
                  status: 'error',
                  error: errorMessage(cause, '일정을 확인하지 못했습니다.'),
                }
              : s,
          ),
        )
      }
    },
    [suggestions],
  )

  const accept = useCallback(
    async (suggestion: AiSuggestionReady, overrideDateISO?: string) => {
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
  }, [])

  return {
    suggestions,
    previewId,
    setPreviewId,
    refreshing,
    error,
    refresh,
    expand,
    accept,
    dismiss,
  }
}
