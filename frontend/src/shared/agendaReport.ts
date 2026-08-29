// 일정 하나에서 보고서로 가는 길. 하루 목록(DayAgenda)과 상세 드로어(RecordDrawer)가
// 같은 곳을 가리켜야 하므로 문구를 여기 한 곳에 둡니다.
//
// 일정 하나가 곧 업무보고서 하나입니다.
//
// 물어볼 일정을 인자로 받습니다. 이 길이 화면에 나타나는 자리는 눌러야 열리는 메뉴
// 한 줄과 드로어 푸터뿐이라, 열기 전에는 아무것도 부르지 않습니다. 대시보드에 들어서자마자
// 보고서를 통째로 받아 두면 열지도 않을 메뉴의 값을 매번 나르게 됩니다.
import { useCallback, useEffect, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import { useCurrentUser } from '@/auth/sessionContext'
import { meetingComposePath, meetingReportPath } from '@/constants/routes'
import { savedForAgenda } from '@/pages/Meetings/useMeetingReports'
import { isOwnAgendaItem } from '@/shared/agenda'
import type { AgendaItem } from '@/types'

export interface AgendaReportLink {
  to: string
  label: string
  /** 이미 쓴 보고서가 있는지. '보고서 미작성' 표시가 이 값을 봅니다. */
  written: boolean
  /**
   * 아직 보고서가 없는데 내가 쓸 수 있는 일정도 아닌 경우입니다. 갈 곳이 없습니다.
   *
   * null 로 두면 부르는 쪽이 아직 답을 못 받은 것과 구분하지 못해 로딩 표시가
   * 영영 남습니다. 확인이 끝났다는 것과 갈 곳이 없다는 것을 함께 말합니다.
   */
  blocked?: true
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
  const { memberId, isManager } = useCurrentUser()
  // item 은 렌더마다 새 객체일 수 있어 보는 값만 꺼내 둡니다.
  const id = item?.id
  const ownerMemberId = item?.ownerMemberId
  // 이미 쓴 보고서는 팀장도 엽니다. 조회이기 때문입니다. 막는 것은 '작성' 뿐입니다.
  const canWrite = item === null || isOwnAgendaItem({ ownerMemberId }, memberId, isManager)

  useEffect(() => {
    setLink(null)
    setError(null)
    if (id === undefined) return
    const controller = new AbortController()
    setLoading(true)
    // 받아 둔 목록에서 찾으면 그 보고서가 목록 페이지 밖일 때 못 찾고 '미작성' 으로 서서
    // 같은 일정에 보고서를 하나 더 만들게 합니다. 서버에 직접 물어야 합니다.
    void savedForAgenda(id, controller.signal)
      .then((row) => {
        if (controller.signal.aborted) return
        setLink(
          row
            ? { to: meetingReportPath(row.id), label: '업무보고서 열기', written: true }
            : canWrite
              ? { to: meetingComposePath(id), label: '업무보고서 작성', written: false }
              : { to: '', label: '', written: false, blocked: true },
        )
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
  }, [id, canWrite, reloadKey])

  const reload = useCallback(() => setReloadKey((value) => value + 1), [])
  return { link, loading, error, reload }
}
