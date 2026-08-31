import { useCallback, useMemo, useState } from 'react'

import { dismissNextMeetingSuggestion, listNextMeetingSuggestions } from '@/api/contractAgent'
import { errorMessage } from '@/api/errorMessage'
import { durationLabel, kstParts } from '@/shared/agenda'
import { RISK_LABEL } from '@/shared/riskLabels'
import type {
  AgendaItem,
  AiSuggestion,
  AiSuggestionOption,
  CalendarEvent,
  ContractNextMeetingSuggestion,
} from '@/types'

type NewEvent = Partial<Omit<CalendarEvent, 'id'>> & { date: string; title: string }
type AddEvent = (draft: NewEvent) => Promise<AgendaItem>

/** priority 오름차순(1이 가장 추천)으로 고른 시간 후보. */
function toOptions(item: ContractNextMeetingSuggestion): AiSuggestionOption[] {
  return [...item.schedule_candidates]
    .sort((a, b) => a.priority - b.priority)
    .map((candidate) => {
      const start = kstParts(candidate.starts_at)
      return {
        candidateId: candidate.candidate_id,
        date: start.date,
        time: start.time,
        dur: durationLabel(candidate.starts_at, candidate.ends_at),
        startsAt: candidate.starts_at,
        endsAt: candidate.ends_at,
        title: candidate.title,
        priority: candidate.priority,
      }
    })
}

function toAiSuggestion(
  item: ContractNextMeetingSuggestion,
  selectedCandidateId: string | undefined,
): AiSuggestion | null {
  const options = toOptions(item)
  if (options.length === 0) return null
  // 고른 것이 없으면 가장 추천하는 후보를 쓴다.
  const chosen = options.find((o) => o.candidateId === selectedCandidateId) ?? options[0]
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
    date: chosen.date,
    time: chosen.time,
    dur: chosen.dur,
    startsAt: chosen.startsAt,
    endsAt: chosen.endsAt,
    place: '',
    activityTitle: chosen.title,
    proposalReason: item.reason,
    basis: [...new Set(item.risks.map((risk) => RISK_LABEL[risk.code]))],
    scheduleRunId: item.schedule_management_run_id,
    options,
    selectedCandidateId: chosen.candidateId,
  }
}

/**
 * 캘린더 "AI 추천 일정" 패널의 데이터·동작을 소유한다.
 *
 * 트리거(보고서 확정·일정 수동 등록·영업 딜 생성/이동·CS 처리 시작)가 서버에서 미리
 * 계산해 저장해 둔 제안을 조회만 한다 — LLM을 직접 호출하지 않으므로 화면이 바로 뜬다.
 * 자세한 배경은 docs/technical/multiagent/계약에이전트_설계.md 11장 참고.
 */
export default function useAiSuggestions(addEvent: AddEvent) {
  // 서버에서 받은 원본을 그대로 들고, 선택은 따로 둔다. 후보를 바꿔 골라도 나머지 값은
  // 다시 만들 필요가 없다.
  const [items, setItems] = useState<ContractNextMeetingSuggestion[]>([])
  const [selection, setSelection] = useState<Record<string, string>>({})
  const [previewId, setPreviewId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const suggestions = useMemo(
    () =>
      items
        .map((item) => toAiSuggestion(item, selection[item.sales_deal_id]))
        .filter((item) => item !== null),
    [items, selection],
  )

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setItems(await listNextMeetingSuggestions())
      setSelection({})
    } catch (cause) {
      setError(errorMessage(cause, 'AI 추천을 불러오지 못했습니다.'))
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [])

  /** 카드에서 다른 시간 후보를 고른다. */
  const selectOption = useCallback((suggestionId: string, candidateId: string) => {
    setSelection((current) => ({ ...current, [suggestionId]: candidateId }))
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
      setItems((list) => list.filter((item) => item.sales_deal_id !== suggestion.id))
      return added
    },
    [addEvent],
  )

  const dismiss = useCallback((id: string) => {
    setItems((list) => list.filter((item) => item.sales_deal_id !== id))
    // 서버 반영에 실패해도 화면은 이미 닫힌 채로 둔다 — 다음 조회에서 다시 나타날 뿐이다.
    void dismissNextMeetingSuggestion(id).catch(() => {})
  }, [])

  return {
    suggestions,
    previewId,
    setPreviewId,
    loading,
    error,
    reload,
    selectOption,
    accept,
    dismiss,
  }
}
