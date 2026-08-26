// 일정 하나에서 보고서로 가는 길. 하루 목록(DayAgenda)과 상세 드로어(RecordDrawer)가
// 같은 곳을 가리켜야 하므로 분기와 문구를 여기 한 곳에 둡니다.
//
// 고객을 만난 일은 그 일정 하나를 기록하는 미팅보고서로, 사내 업무는 그날 하루를
// 묶는 일일업무보고로 갑니다. 업무는 일정마다 보고서가 따로 나지 않습니다.
//
// 물어볼 일정을 인자로 받습니다. 이 길이 화면에 나타나는 자리는 눌러야 열리는 메뉴
// 한 줄과 드로어 푸터뿐이라, 열기 전에는 아무것도 부르지 않습니다. 대시보드에 들어서자마자
// 보고서를 통째로 받아 두면 열지도 않을 메뉴의 값을 매번 나르게 됩니다.
import { useCallback, useEffect, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import {
  dailyComposePath,
  dailyReportPath,
  meetingComposePath,
  meetingReportPath,
} from '@/constants/routes'
import { savedIdForPeriod } from '@/pages/Daily/useDailyReports'
import { savedForAgenda } from '@/pages/Meetings/useMeetingReports'
import type { AgendaItem } from '@/types'

export interface AgendaReportLink {
  to: string
  label: string
  /** 이미 쓴 보고서가 있는지. '보고서 미작성' 표시가 이 값을 봅니다. */
  written: boolean
}

/**
 * `item` 이 null 이면 아무것도 부르지 않습니다. 메뉴를 닫아 두는 동안이 그렇습니다.
 * `link` 는 답을 받기 전까지 null 입니다.
 */
export function useAgendaReportLink(item: AgendaItem | null) {
  const [link, setLink] = useState<AgendaReportLink | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  // item 은 렌더마다 새 객체일 수 있어 보는 값만 꺼내 둡니다.
  const internal = item?.kind === 'internal'
  const id = item?.id
  const date = item?.date

  useEffect(() => {
    setLink(null)
    setError(null)
    if (id === undefined || date === undefined) return
    const controller = new AbortController()
    setLoading(true)
    // 받아 둔 목록에서 찾으면 그 보고서가 목록 페이지 밖일 때 못 찾고 '미작성' 으로 서서
    // 같은 일정에 보고서를 하나 더 만들게 합니다. 서버에 직접 물어야 합니다.
    const ask = internal
      ? savedIdForPeriod('일일', date, controller.signal)
      : savedForAgenda(id, controller.signal).then((row) => row?.id)
    void ask
      .then((savedId) => {
        if (controller.signal.aborted) return
        if (internal) {
          setLink(
            savedId
              ? { to: dailyReportPath(savedId), label: '일일업무보고 열기', written: true }
              : { to: dailyComposePath(date, '일일'), label: '업무보고 작성', written: false },
          )
        } else {
          setLink(
            savedId
              ? { to: meetingReportPath(savedId), label: '미팅보고서 열기', written: true }
              : { to: meetingComposePath(id), label: '미팅보고서 작성', written: false },
          )
        }
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(errorMessage(reason, '보고서 연결을 확인하지 못했습니다.'))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [internal, id, date, reloadKey])

  const reload = useCallback(() => setReloadKey((value) => value + 1), [])
  return { link, loading, error, reload }
}
