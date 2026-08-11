import { ArrowDownIcon } from '@/components/icons'
import { agendaFor } from '@/content/agenda'
import { csRequests, followUps, renewals, salesGoal } from '@/content/counters'
import { TODAY_ISO } from '@/utils/date'
import { won } from '@/utils/format'

import styles from './SummaryBand.module.scss'

/**
 * KPI 숫자는 전부 src/content 의 목록에서 파생됩니다.
 *
 * 상수로 박아 두면 타일과 그 뒤에 붙을 목록이 어긋날 수 있습니다. 다음 작업에서
 * 타일을 눌러 여는 드로어가 같은 목록을 그대로 쓰게 됩니다.
 */
function deriveCounters() {
  const todayList = agendaFor(TODAY_ISO)
  const external = todayList.filter((it) => it.kind !== 'internal')
  const orgs = new Set(external.map((it) => it.hospital))

  return {
    visits: {
      count: orgs.size,
      sub: `오늘 일정 ${todayList.length}건 · 외부 ${external.length}건`,
    },
    followUp: {
      count: followUps.length,
      late: followUps.filter((f) => f.dueOff < 0).length,
      sub: `이번 주 마감 ${followUps.filter((f) => f.dueOff >= 0 && f.dueOff <= 7).length}건`,
    },
    cs: {
      count: csRequests.length,
      urgent: csRequests.filter((c) => c.urgent).length,
      sub:
        `미응답 ${csRequests.filter((c) => c.state === '미응답').length}건 · ` +
        `처리중 ${csRequests.filter((c) => c.state === '처리중').length}건`,
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
}

function Tile({ label, delta, value, sub }: TileProps) {
  return (
    <article className={styles.kpi}>
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
    </article>
  )
}

export default function SummaryBand({ onJumpToToday }: { onJumpToToday: () => void }) {
  const c = deriveCounters()
  const percent = (salesGoal.achieved / salesGoal.target) * 100

  return (
    <div className={styles.summary}>
      {/* 이 타일만 클릭이 살아 있습니다. 답이 이미 페이지 안에 있어 아젠다로
          내려보내면 되고, 드로어가 필요 없습니다. */}
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
      />
      <Tile
        label="C/S 대응요청"
        delta={{ text: `긴급 ${c.cs.urgent}건`, tone: 'danger' }}
        value={c.cs.count}
        sub={c.cs.sub}
      />
      <Tile
        label="계약갱신 예정"
        delta={{ text: '30일 이내', tone: 'warn' }}
        value={c.renewal.count}
        sub={c.renewal.sub}
      />

      <article className={styles.goal} aria-label={`${salesGoal.month}월 매출 목표`}>
        <div className={styles.goalHead}>
          <span>{salesGoal.month}월 매출 목표</span>
          <strong className="tnum">{percent.toFixed(1)}%</strong>
        </div>
        <p className={`${styles.goalValue} tnum`}>
          {won(salesGoal.achieved)} <em>/ {won(salesGoal.target)}</em>
        </p>
        <div className={styles.goalTrack}>
          <i style={{ '--p': `${percent}%` } as React.CSSProperties} />
        </div>
        <div className={styles.goalFoot}>
          <span>{salesGoal.teamName}</span>
          <span className="tnum">마감 D-{salesGoal.deadlineInDays}</span>
        </div>
      </article>
    </div>
  )
}
