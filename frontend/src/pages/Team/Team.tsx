// 팀 관리. 구성원의 역할·재직 상태와 매출 목표를 다룹니다.
//
// 화면을 세 단으로 세웁니다. 이번 달 팀의 숫자(GoalBand), 지금 손봐야 할 사람
// (AttentionCard), 그리고 구성원별 진척(표)입니다. 팀장이 위에서 아래로 한 번 훑으면
// 무엇부터 할지가 정해지도록 둔 순서입니다.
//
// 목표를 고치면 대시보드의 매출 목표 타일도 같은 값을 보게 됩니다. 달성률은 서버가 셈해
// 준 것을 그대로 씁니다. 화면에서 다시 계산하면 두 화면의 숫자가 갈라집니다.
//
// 고치는 일은 줄 안에서 하지 않고 상세 드로어에서 합니다. 목표·역할·재직 상태를 한 줄에
// 늘어놓으면 표가 입력 폼이 되어 읽기가 어려워집니다. 드로어는 줄 아무 곳이나 눌러 엽니다.
import { useMemo, useState } from 'react'

import { useCurrentUser } from '@/auth/sessionContext'
import ErrorToast from '@/components/ErrorToast'
import { ListPageSkeleton, TableSkeleton } from '@/components/Skeleton'
import type { SelectOption } from '@/components/Select'
import StatusBadge from '@/components/StatusBadge'
import type { TeamMemberRow } from '@/types'

import AttentionCard from './components/AttentionCard'
import GoalBand from './components/GoalBand'
import MemberDrawer from './components/MemberDrawer'
import MemberRow from './components/MemberRow'
import useTeamOverview from './useTeamOverview'

import styles from './Team.module.scss'

/** 이번 달 1일. 목표는 월 단위라 언제나 그달 첫날을 기준으로 봅니다. */
function thisMonth(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
}

/** 이번 달부터 거슬러 열두 달. 목표는 지난달 것도 들여다봐야 할 때가 있습니다. */
function monthOptions(): SelectOption[] {
  const now = new Date()
  return Array.from({ length: 12 }, (_, back) => {
    const date = new Date(now.getFullYear(), now.getMonth() - back, 1)
    const year = date.getFullYear()
    const month = date.getMonth() + 1
    return {
      value: `${year}-${String(month).padStart(2, '0')}-01`,
      label: `${year}년 ${month}월`,
    }
  })
}

export default function Team() {
  const { memberId } = useCurrentUser()
  const [targetMonth, setTargetMonth] = useState(thisMonth)
  const [openId, setOpenId] = useState<string | null>(null)

  const { data, loading, error, reload, saveMember } = useTeamOverview(targetMonth)

  const months = useMemo(monthOptions, [])
  const members = useMemo<TeamMemberRow[]>(() => {
    // 자리를 비운 사람이 가운데 끼면 읽는 흐름이 끊깁니다. 순서는 그대로 두고 뒤로만 보냅니다.
    const rows = data?.members ?? []
    return [...rows].sort((a, b) => Number(b.active) - Number(a.active))
  }, [data])

  const open = members.find((member) => member.id === openId) ?? null
  const activeCount = members.filter((member) => member.active).length

  // 첫 진입에서 카드와 표가 따로 들어오면 화면이 두 번 들썩입니다. 한 장을 통째로 둡니다.
  if (loading && data === null && error === null) {
    return (
      <section className={styles.page} aria-busy>
        <h1 className="sr-only">팀 관리</h1>
        <ListPageSkeleton label="팀 정보를 불러오는 중입니다." />
      </section>
    )
  }

  return (
    <section className={styles.page} aria-busy={loading}>
      {/* Topbar 빵부스러기가 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
      <h1 className="sr-only">팀 관리</h1>

      <ErrorToast message={error} onRetry={reload} />

      {data !== null && (
        <GoalBand
          data={data}
          activeCount={activeCount}
          month={targetMonth}
          monthOptions={months}
          onMonthChange={setTargetMonth}
        />
      )}

      <AttentionCard members={members} onOpen={setOpenId} />

      {!error && loading ? (
        <TableSkeleton label="팀 정보를 새로고침하는 중입니다." rows={members.length} />
      ) : (
        <div className={styles.card}>
          <h2 className={styles.cardHead}>구성원별 현황</h2>

          <div className={styles.scroller}>
            <table className={styles.table}>
              <caption className="sr-only">
                팀 구성원 목록. 목표 매출과 달성률을 보고 상세에서 고칠 수 있습니다.
              </caption>
              <thead>
                <tr>
                  <th scope="col">팀원</th>
                  <th scope="col">역할·담당지역</th>
                  <th scope="col">현재 매출 / 목표 매출</th>
                  <th scope="col" className={styles.right}>
                    달성률
                  </th>
                  <th scope="col">상태</th>
                </tr>
              </thead>
              <tbody>
                {members.map((member) => (
                  <MemberRow
                    key={member.id}
                    member={member}
                    isSelf={member.id === memberId}
                    onOpen={() => setOpenId(member.id)}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {members.length === 0 && <p className={styles.empty}>팀에 등록된 구성원이 없습니다.</p>}
        </div>
      )}

      {members.some((member) => !member.active) && (
        <p className={styles.note}>
          <StatusBadge label="비활성" />
          <span>비활성 구성원도 목록에 남깁니다. 상세에서 다시 재직으로 되돌릴 수 있습니다.</span>
        </p>
      )}

      {open !== null && (
        <MemberDrawer
          member={open}
          isSelf={open.id === memberId}
          targetMonth={targetMonth.slice(0, 7)}
          onSave={saveMember}
          onClose={() => setOpenId(null)}
        />
      )}
    </section>
  )
}
