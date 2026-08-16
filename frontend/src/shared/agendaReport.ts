// 일정 하나에서 보고서로 가는 길. 하루 목록(DayAgenda)과 상세 드로어(RecordDrawer)가
// 같은 곳을 가리켜야 하므로 분기와 문구를 여기 한 곳에 둡니다.
//
// 고객을 만난 일은 그 일정 하나를 기록하는 미팅보고서로, 사내 업무는 그날 하루를
// 묶는 일일업무보고로 갑니다. 업무는 일정마다 보고서가 따로 나지 않습니다.
import { useCallback } from 'react'

import {
  dailyComposePath,
  dailyReportPath,
  meetingComposePath,
  meetingReportPath,
} from '@/constants/routes'
import useDailyReports from '@/pages/Daily/useDailyReports'
import useMeetingReports from '@/pages/Meetings/useMeetingReports'
import type { AgendaItem } from '@/types'

export interface AgendaReportLink {
  to: string
  label: string
  /** 이미 쓴 보고서가 있는지. 목록의 '미작성' 표시가 이 값을 봅니다. */
  written: boolean
}

export function useAgendaReportLink(): (item: AgendaItem) => AgendaReportLink {
  const { findByAgenda } = useMeetingReports()
  const { findByDate } = useDailyReports()

  return useCallback(
    (item: AgendaItem) => {
      if (item.kind === 'internal') {
        const saved = findByDate(item.date, '일일')
        return saved
          ? { to: dailyReportPath(saved.id), label: '일일업무보고 열기', written: true }
          : { to: dailyComposePath(item.date, '일일'), label: '일일업무보고 작성', written: false }
      }

      const saved = findByAgenda(item.id)
      return saved
        ? { to: meetingReportPath(saved.id), label: '미팅보고서 열기', written: true }
        : { to: meetingComposePath(item.id), label: '미팅보고서 작성', written: false }
    },
    [findByAgenda, findByDate],
  )
}
