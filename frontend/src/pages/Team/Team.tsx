// 팀 관리. 구성원의 역할·재직 상태와 매출 목표를 다룹니다.
//
// 화면 하나에 "팀이 이번 달 얼마를 목표하고 지금 얼마까지 왔는가" 와 "누가 어디까지 왔는가"
// 를 함께 둡니다. 목표를 고치면 대시보드의 매출 목표 타일도 같은 값을 보게 됩니다. 달성률은
// 서버가 셈해 준 것을 그대로 씁니다. 화면에서 다시 계산하면 두 화면의 숫자가 갈라집니다.
//
// 고치는 일은 줄 안에서 하지 않고 상세 드로어에서 합니다. 목표·역할·재직 상태를 한 줄에
// 늘어놓으면 표가 입력 폼이 되어 읽기가 어려워집니다.
import { useMemo, useState } from 'react'

import { useCurrentUser } from '@/auth/sessionContext'
import ErrorToast from '@/components/ErrorToast'
import { InlineLoader, ListPageSkeleton } from '@/components/Skeleton'
import StatusBadge from '@/components/StatusBadge'
import type { TeamMemberRow } from '@/types'
import { wonFull } from '@/utils/format'

import MemberDrawer from './components/MemberDrawer'
import MemberRow from './components/MemberRow'
import useTeamOverview from './useTeamOverview'

import styles from './Team.module.scss'

/** 이번 달 1일. 목표는 월 단위라 언제나 그달 첫날을 기준으로 봅니다. */
function thisMonth(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
}

export default function Team() {
  const { memberId } = useCurrentUser()
  const [targetMonth] = useState(thisMonth)
  const [openId, setOpenId] = useState<string | null>(null)

  const { data, loading, error, reload, saveMember } = useTeamOverview(targetMonth)

  const members = useMemo<TeamMemberRow[]>(() => data?.members ?? [], [data])
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
        <div className={styles.goal}>
          <div className={styles.goalHead}>
            <h2 className={styles.goalTitle}>팀 목표 매출</h2>
            <span className={styles.goalMonth}>{data.target_month}</span>
          </div>

          <div className={styles.goalStats}>
            <p className={styles.stat}>
              <span>월 목표 매출</span>
              <strong className="tnum">{wonFull(data.team_target)}</strong>
            </p>
            <p className={styles.stat}>
              <span>현재 매출</span>
              <strong className="tnum">{wonFull(data.team_confirmed)}</strong>
            </p>
            <p className={styles.stat}>
              <span>달성률</span>
              <strong className="tnum">
                {/* 목표를 세우지 않은 것과 아직 못 채운 것은 다릅니다. */}
                {data.team_rate === null ? '목표 미설정' : `${data.team_rate}%`}
              </strong>
            </p>
          </div>

          {/* 대시보드 매출 목표 타일과 같은 막대입니다. 목표를 넘어선 만큼은 막대 밖으로
              나갈 자리가 없으므로 막대를 채우고 색으로 알립니다. */}
          <div
            className={`${styles.goalTrack} ${(data.team_rate ?? 0) > 100 ? styles.isOver : ''}`}
            style={{ '--p': `${Math.min(100, data.team_rate ?? 0)}%` } as React.CSSProperties}
          >
            <i />
          </div>

          <p className={styles.goalFoot}>
            <span>재직 중인 구성원 {activeCount}명</span>
            {/* 지금은 팀 목표를 따로 세우지 않고 팀원 목표를 더해 씁니다. 두 값을 나눠
                보여 주어야 나중에 팀 목표를 따로 넣게 되어도 화면이 그대로입니다. */}
            <span className="tnum">팀원 목표 합계 {wonFull(data.member_target_sum)}</span>
          </p>
        </div>
      )}

      {!error && loading && data !== null && (
        <InlineLoader label="팀 정보를 새로고침하는 중입니다." />
      )}

      <div className={styles.card}>
        <div className={styles.scroller}>
          <table className={styles.table}>
            <caption className="sr-only">
              팀 구성원 목록. 목표 매출과 달성률을 보고 상세에서 고칠 수 있습니다.
            </caption>
            <thead>
              <tr>
                <th scope="col">팀원</th>
                <th scope="col">직책</th>
                <th scope="col">역할</th>
                <th scope="col" className={styles.right}>
                  목표 매출
                </th>
                <th scope="col" className={styles.right}>
                  현재 매출
                </th>
                <th scope="col">달성률</th>
                <th scope="col">상태</th>
                <th scope="col">
                  <span className="sr-only">관리</span>
                </th>
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

        {members.length === 0 && !loading && (
          <p className={styles.empty}>팀에 등록된 구성원이 없습니다.</p>
        )}
      </div>

      {members.some((member) => !member.active) && (
        <p className={styles.note}>
          <StatusBadge label="비활성" />
          <span>
            비활성 구성원도 목록에 남깁니다. 상세에서 다시 재직으로 되돌릴 수 있습니다.
          </span>
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
