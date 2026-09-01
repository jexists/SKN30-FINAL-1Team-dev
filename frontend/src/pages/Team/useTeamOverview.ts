// 팀 관리 화면의 데이터원.
//
// 목표와 실적을 서버가 한 번에 셈해 줍니다. 달성률을 화면에서 다시 계산하지 않는 까닭은,
// 대시보드의 매출 목표 타일과 숫자가 갈라지면 팀장이 어느 쪽을 믿을지 알 수 없기 때문입니다.
import { useCallback, useEffect, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import type { TeamMemberPatchRequest, TeamMemberRow, TeamOverviewResponse } from '@/types'

export default function useTeamOverview(targetMonth: string) {
  const [data, setData] = useState<TeamOverviewResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    void client
      .get<TeamOverviewResponse>('/team/members', {
        params: { target_month: targetMonth },
        signal: controller.signal,
      })
      .then((response) => {
        if (controller.signal.aborted) return
        setData(response.data)
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          setError(errorMessage(caught, '팀 정보를 불러오지 못했습니다.'))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [targetMonth, reloadKey])

  const reload = useCallback(() => setReloadKey((previous) => previous + 1), [])

  const saveMember = useCallback(
    async (memberId: string, patch: TeamMemberPatchRequest) => {
      const { data: row } = await client.patch<TeamMemberRow>(`/team/members/${memberId}`, {
        ...patch,
        target_month: targetMonth,
      })
      setReloadKey((previous) => previous + 1)
      return row
    },
    [targetMonth],
  )

  return { data, loading, error, reload, saveMember }
}
