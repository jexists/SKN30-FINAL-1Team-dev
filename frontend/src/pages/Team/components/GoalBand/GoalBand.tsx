// 팀 관리 첫 단. 이번 달 팀의 숫자를 네 조각으로 세웁니다.
//
// 대시보드 매출 목표 타일과 같은 막대(--p/--mark/--split)를 씁니다. 같은 값을 두 화면이
// 다른 모양으로 그리면 팀장이 둘을 견주지 못합니다. 달성률은 언제나 서버가 셈해 준 값입니다.
//
// 타일은 누르는 곳이 아닙니다. 이 화면에서 실제로 열리는 것은 아래 구성원 줄뿐이라
// 대시보드와 달리 button 이 아닌 글상자로 두고 hover 도 넣지 않습니다.
import Select, { type SelectOption } from '@/components/Select'
import type { StatusTone } from '@/components/StatusBadge'
import type { TeamOverviewResponse } from '@/types'
import { wonFull } from '@/utils/format'

import { health } from '../../health'

import styles from './GoalBand.module.scss'

// 칩 색은 목록의 상태 배지와 같은 눈금(health)을 씁니다. 위 카드는 주황인데 아래 배지는
// 초록이면, 한 화면이 같은 숫자를 두고 서로 다른 말을 하게 됩니다.
const CHIP: Partial<Record<StatusTone, string>> = {
  green: styles.good,
  orange: styles.warn,
  red: styles.bad,
}

interface Props {
  data: TeamOverviewResponse
  /** 재직 중인 구성원 수. 목록에서 세어 넘깁니다. */
  activeCount: number
  /** 'YYYY-MM-01' */
  month: string
  monthOptions: readonly SelectOption[]
  onMonthChange: (month: string) => void
}

/** 이 달 말일까지 남은 일수. 지난달을 보고 있으면 셈하지 않습니다. */
function daysLeftIn(month: string): number | null {
  const now = new Date()
  const current = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
  if (month !== current) return null
  const last = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate()
  return last - now.getDate()
}

export default function GoalBand({ data, activeCount, month, monthOptions, onMonthChange }: Props) {
  const target = data.team_target
  const confirmed = data.team_confirmed
  // 목표가 없으면 0% 가 아니라 '미설정' 입니다. 서버가 달성률을 null 로 갈라 줍니다.
  const hasTarget = data.team_rate !== null
  const percent = data.team_rate ?? 0
  const remaining = Math.max(0, target - confirmed)
  const surplus = confirmed - target
  const daysLeft = daysLeftIn(month)

  // 목표를 넘기면 트랙이 100% 가 아니라 달성률 전체를 담습니다. 그래야 막대가 잘리지 않고
  // 100% 눈금이 트랙 안에 남아 얼마나 넘었는지가 길이로 읽힙니다.
  const trackMax = Math.max(percent, 100)
  const over = hasTarget && surplus > 0
  const tone = health(data.team_rate).tone

  return (
    <section className={styles.band} aria-labelledby="team-goal-heading">
      <div className={styles.head}>
        <h2 id="team-goal-heading" className={styles.title}>
          팀 목표 매출
        </h2>
        <Select
          label="기준 월"
          size="sm"
          value={month}
          options={monthOptions}
          onChange={onMonthChange}
          className={styles.month}
        />
      </div>

      <div className={styles.tiles}>
        <div className={styles.tile}>
          <span className={styles.label}>팀 목표</span>
          <strong className="tnum">{wonFull(target)}</strong>
          {/* 지금은 팀 목표를 따로 세우지 않고 팀원 목표를 더해 씁니다. 두 값을 나눠 두면
              나중에 팀 목표를 따로 넣게 되어도 이 자리가 그대로 남습니다. */}
          <small className="tnum">팀원 목표 합계 {wonFull(data.member_target_sum)}</small>
        </div>

        <div className={styles.tile}>
          <span className={styles.label}>현재 매출</span>
          <strong className="tnum">{wonFull(confirmed)}</strong>
          <small>
            {hasTarget ? (
              <i className={`${styles.chip} ${CHIP[tone] ?? ''}`}>목표의 {percent}%</i>
            ) : (
              '이번 달 확정된 계약 금액'
            )}
          </small>
        </div>

        <div className={styles.tile}>
          <span className={styles.label}>{over ? '목표 초과' : '목표까지'}</span>
          <strong className="tnum">{hasTarget ? wonFull(over ? surplus : remaining) : '—'}</strong>
          <small>
            {!hasTarget
              ? '목표를 정하면 남은 금액이 나옵니다'
              : daysLeft === null
                ? `${data.target_month} 기준`
                : daysLeft === 0
                  ? '오늘이 이달 마지막 날입니다'
                  : `이번 달 ${daysLeft}일 남음`}
          </small>
        </div>

        <div className={`${styles.tile} ${over ? styles.isOver : ''}`}>
          <span className={styles.label}>달성률</span>
          <strong className={hasTarget ? 'tnum' : styles.soft}>
            {hasTarget ? `${percent}%` : '목표 미설정'}
          </strong>
          {hasTarget && (
            <div
              className={styles.track}
              style={
                {
                  '--p': `${(percent / trackMax) * 100}%`,
                  '--mark': `${(100 / trackMax) * 100}%`,
                  '--split': percent > 0 ? `${(100 / percent) * 100}%` : '100%',
                } as React.CSSProperties
              }
            >
              <i />
            </div>
          )}
          <small>재직 중인 구성원 {activeCount}명</small>
        </div>
      </div>
    </section>
  )
}
