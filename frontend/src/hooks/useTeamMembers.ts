import { useEffect, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import type { TeamMemberOption } from '@/types'

interface TeamMembersState {
  members: TeamMemberOption[]
  loading: boolean
  loadError: string | null
  reload: () => void
}

/**
 * 같은 팀의 활성 구성원 목록입니다.
 *
 * 팀 하나의 인원이라 한 번 받아 두고 검색은 화면에서 거릅니다. `enabled` 가 false 면
 * 부르지 않습니다. 목록이 닫혀 있는 동안 미리 받아 둘 이유가 없습니다.
 */
export default function useTeamMembers(enabled = true): TeamMembersState {
  const [members, setMembers] = useState<TeamMemberOption[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    if (!enabled) return

    const controller = new AbortController()
    setLoading(true)
    setLoadError(null)

    void client
      .get<TeamMemberOption[]>('/team-members', { signal: controller.signal })
      .then(({ data }) => {
        if (!controller.signal.aborted) setMembers(data)
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return
        setMembers([])
        setLoadError(errorMessage(reason, '팀원 목록을 불러오지 못했습니다.'))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [enabled, reloadKey])

  return { members, loading, loadError, reload: () => setReloadKey((value) => value + 1) }
}
