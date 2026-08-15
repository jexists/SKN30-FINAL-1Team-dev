import { useCallback } from 'react'

import {
  addAgenda,
  agendaByDate,
  agendaById,
  removeAgenda,
  updateAgenda,
  useAgenda,
} from '@/shared/agenda'
import type { AgendaItem, CalendarEvent } from '@/types'
import { useCurrentUser } from '@/auth/sessionContext'

// 일정 목록 자체는 shared/agenda.ts 한 곳에 있습니다. 대시보드와 캘린더가 같은
// 목록을 보게 하려고 여기서는 그 스토어를 캘린더의 어휘로 감싸기만 합니다.
// 백엔드가 붙는 지점도 그쪽 mutator 셋입니다.

/** 새 일정의 기본값. 인라인 추가는 제목만 받고 나머지는 여기서 채웁니다. */
export const DEFAULTS = { time: '09:00', dur: '1시간', kind: 'internal', done: false } as const

/**
 * 화면에서 만든 일정에는 시드가 들고 있는 영업 맥락이 없습니다. 빈 값으로 두면
 * 드로어·목록이 그 칸을 아예 그리지 않습니다.
 *
 * reported 를 true 로 두는 이유: 방금 만든 일정을 곧바로 '보고서 미작성' 으로
 * 몰지 않기 위함입니다. 실제 보고 여부는 useMeetingReports 가 따로 봅니다.
 */
const BLANK = () => ({
  off: 0,
  hospital: '',
  dept: '',
  contact: '',
  product: '',
  place: '',
  brief: '',
  history: [],
  tags: [],
  reported: true,
})

// Date.now() 는 같은 밀리초 안에 두 번 부르면 같은 값이 나옵니다. id 가 겹치면
// 드래그가 엉뚱한 일정을 옮기고 React 키도 중복되므로 증가하는 번호를 씁니다.
let seq = 0

type NewEvent = Partial<Omit<CalendarEvent, 'id'>> & { date: string; title: string }

export default function useCalendarEvents() {
  // 목록이 바뀌면 이 훅을 쓰는 화면이 다시 그려집니다.
  useAgenda()
  const { profile } = useCurrentUser()

  const addEvent = useCallback(
    (draft: NewEvent) => {
      // 목업이라 서버가 id 를 주지 않습니다. 화면 안에서만 겹치지 않으면 됩니다.
      // owner 는 로그인한 사람입니다. 비어 있으면 프로필 필터에서 일정이 사라집니다.
      const item: AgendaItem = {
        ...BLANK(),
        ...DEFAULTS,
        owner: profile.name,
        ...draft,
        id: `ce-${++seq}`,
      }
      addAgenda(item)
      return item
    },
    [profile.name],
  )

  /** 모달이 돌려주는 것은 느슨한 CalendarEvent 라, 원본에 덮어써야 나머지 칸이 남습니다. */
  const updateEvent = useCallback((next: CalendarEvent) => {
    const current = agendaById(next.id)
    if (current) updateAgenda({ ...current, ...next })
  }, [])

  /** 날짜만 옮깁니다. 시간은 그대로 두어 그날 안에서의 순서가 유지됩니다. */
  const moveEvent = useCallback((id: string, date: string) => {
    const current = agendaById(id)
    if (current && current.date !== date) updateAgenda({ ...current, date })
  }, [])

  const removeEvent = useCallback((id: string) => removeAgenda(id), [])

  const toggleDone = useCallback((id: string) => {
    const current = agendaById(id)
    if (current) updateAgenda({ ...current, done: !current.done })
  }, [])

  return { eventsByDate: agendaByDate(), addEvent, updateEvent, moveEvent, removeEvent, toggleDone }
}
