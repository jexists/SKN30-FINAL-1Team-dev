import { ArrowDownIcon } from '@/components/icons'
import { agendaFor, useAgenda } from '@/shared/agenda'
import { csRequests, followUps, renewals, salesGoal } from '@/shared/counters'
import { TODAY_ISO } from '@/utils/date'
import { won } from '@/utils/format'

import type { KpiListKey } from '../../drawerLists'

import styles from './SummaryBand.module.scss'

/**
 * KPI 숫자는 전부 src/content 의 목록에서 파생됩니다.
 *
 * 상수로 박아 두면 타일과 그 뒤의 목록이 어긋날 수 있습니다. 타일을 누르면 여는
 * 드로어가 여기서 센 것과 같은 목록을 그대로 펼칩니다(drawerLists.ts).
 */
function deriveCounters() {
  const todayList = agendaFor(TODAY_ISO)
  const external = todayList.filter((it) => it.kind !== 'internal')
  const orgs = new Set(external.map((it) => it.hospital))

  return {
    visits: {
      count: orgs.size,
      sub: `오늘 일정 ${todayList.length}건`,
    },
    followUp: {
      count: followUps.length,
      late: followUps.filter((f) => f.dueOff < 0).length,
      sub: `이번 주 마감 ${followUps.filter((f) => f.dueOff >= 0 && f.dueOff <= 7).length}건`,
    },
    cs: {
      count: csRequests.length,
      urgent: csRequests.filter((c) => c.urgent).length,
      sub: `처리중 ${csRequests.filter((c) => c.state === '처리중').length}건`,
    },
    renewal: {
      count: renewals.length,
      sub:
        renewals.length > 1
          ? `${renewals[0].org} 외 ${renewals.length - 1}곳`
          : (renewals[0]?.org ?? '—'),
    },
  }
}

interface TileProps {
  label: string
  delta?: { text: string; tone?: 'warn' | 'danger' }
  value: number
  sub: string
  onOpen: () => void
}

function Tile({ label, delta, value, sub, onOpen }: TileProps) {
  return (
    <button type="button" className={styles.kpi} onClick={onOpen}>
      <span className={styles.top}>
        <span>{label}</span>
        {delta && (
          <i className={[styles.delta, delta.tone && styles[delta.tone]].filter(Boolean).join(' ')}>
            {delta.text}
          </i>
        )}
      </span>
      <strong className="tnum">{value}</strong>
      <span className={styles.foot}>
        <small>{sub}</small>
      </span>
    </button>
  )
}

interface Props {
  onJumpToToday: () => void
  onOpenList: (key: KpiListKey) => void
}

export default function SummaryBand({ onJumpToToday, onOpenList }: Props) {
  // 일정이 늘거나 줄면 '오늘 방문 회사' 타일이 따라 움직여야 합니다.
  useAgenda()
  const c = deriveCounters()
  const percent = (salesGoal.achieved / salesGoal.target) * 100
  const over = salesGoal.achieved >= salesGoal.target
  // 목표를 넘기면 트랙이 100%가 아니라 달성률 전체를 담습니다. 그래야 막대가 잘리지 않고
  // 100% 눈금이 트랙 안쪽에 남아 "얼마나 넘었는지"가 길이로 읽힙니다.
  const trackMax = Math.max(percent, 100)
  const surplus = salesGoal.achieved - salesGoal.target

  return (
    <div className={styles.summary}>
      {/* 이 타일만 드로어를 열지 않습니다. 답이 이미 페이지 안에 있어
          아젠다로 내려보내면 됩니다. */}
      <button type="button" className={`${styles.kpi} ${styles.jump}`} onClick={onJumpToToday}>
        <span className={styles.top}>
          <span>오늘 방문 회사</span>
        </span>
        <strong className="tnum">{c.visits.count}</strong>
        <span className={styles.foot}>
          <small>{c.visits.sub}</small>
          <ArrowDownIcon className={styles.cue} width={14} height={14} />
        </span>
      </button>

      <Tile
        label="미완료 후속업무"
        delta={{ text: `${c.followUp.late} 지연`, tone: 'warn' }}
        value={c.followUp.count}
        sub={c.followUp.sub}
        onOpen={() => onOpenList('followUp')}
      />
      <Tile
        label="C/S 대응요청"
        delta={{ text: `긴급 ${c.cs.urgent}건`, tone: 'danger' }}
        value={c.cs.count}
        sub={c.cs.sub}
        onOpen={() => onOpenList('cs')}
      />
      <Tile
        label="계약갱신 예정"
        delta={{ text: '30일 이내', tone: 'warn' }}
        value={c.renewal.count}
        sub={c.renewal.sub}
        onOpen={() => onOpenList('renewal')}
      />

      <article
        className={[styles.goal, over && styles.over].filter(Boolean).join(' ')}
        aria-label={`${salesGoal.month}월 매출 목표${over ? ' — 목표 달성' : ''}`}
      >
        <div className={styles.goalHead}>
          <span>{salesGoal.month}월 매출 목표</span>
          {over && <i className={styles.delta}>목표 달성</i>}
          <strong className="tnum">{percent.toFixed(1)}%</strong>
        </div>
        <p className={`${styles.goalValue} tnum`}>
          {won(salesGoal.achieved)} <em>/ {won(salesGoal.target)}</em>
        </p>
        <div
          className={styles.goalTrack}
          style={
            {
              '--p': `${(percent / trackMax) * 100}%`,
              // 트랙 안에서의 100% 눈금 위치와, 막대 안에서 색이 갈리는 지점.
              '--mark': `${(100 / trackMax) * 100}%`,
              // 실적이 0이면 나눌 지점이 없습니다. 막대 전체를 미달성 색으로 둡니다.
              '--split': percent > 0 ? `${(100 / percent) * 100}%` : '100%',
            } as React.CSSProperties
          }
        >
          <i />
        </div>
        <div className={styles.goalFoot}>
          <span>{salesGoal.teamName}</span>
          <span className={`tnum ${surplus > 0 ? styles.surplus : ''}`}>
            {/* 딱 맞춰 달성한 경우엔 초과분 대신 남은 기간을 그대로 둡니다.
                '초과 +₩0' 은 읽는 사람에게 아무것도 알려 주지 않습니다. */}
            {surplus > 0 ? `목표 초과 +${won(surplus)}` : `마감 D-${salesGoal.deadlineInDays}`}
          </span>
        </div>
      </article>
    </div>
  )
}
