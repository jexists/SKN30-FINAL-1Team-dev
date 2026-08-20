import { Link } from 'react-router'

import { ArrowDownIcon } from '@/components/icons'
import { ROUTES } from '@/constants/routes'
import type { SalesDeal } from '@/pages/Deals/useSalesDeals'
import { agendaFor, useAgenda } from '@/shared/agenda'
import { followUps, salesGoal } from '@/shared/counters'
import { monthlyTotal } from '@/shared/salesTargets'
import type { SupportRequestResponse } from '@/types'
import { addDays, ddayLabel, endOfMonth, iso, startOfMonth, TODAY, TODAY_ISO } from '@/utils/date'
import { won } from '@/utils/format'

import type { KpiListKey } from '../../drawerLists'

import styles from './SummaryBand.module.scss'

interface TileProps {
  label: string
  delta?: { text: string; tone?: 'warn' | 'danger' }
  value: number | string
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
  requests: SupportRequestResponse[]
  deals: SalesDeal[]
  onJumpToToday: () => void
  onOpenList: (key: KpiListKey) => void
}

export default function SummaryBand({ requests, deals, onJumpToToday, onOpenList }: Props) {
  useAgenda()
  const todayList = agendaFor(TODAY_ISO)
  const external = todayList.filter((item) => item.kind !== 'internal')
  const visits = new Set(external.map((item) => item.hospital).filter(Boolean)).size
  const urgent = requests.filter((request) => request.is_urgent).length
  const working = requests.filter((request) => request.status_code === 'in_progress').length
  const renewalEnd = iso(addDays(TODAY, 30))
  const renewals = deals.filter(
    (deal) =>
      deal.contractEndsOn !== null &&
      deal.status !== '취소' &&
      deal.contractEndsOn >= TODAY_ISO &&
      deal.contractEndsOn <= renewalEnd,
  )
  const monthStart = iso(startOfMonth(TODAY))
  const monthEnd = iso(endOfMonth(TODAY))
  const achieved = deals.reduce((sum, deal) => {
    const date = deal.contractSignedOn ?? deal.closedOn
    return deal.status === '확정' && date && date >= monthStart && date <= monthEnd
      ? sum + deal.amount
      : sum
  }, 0)
  const lateFollowUps = followUps.filter((item) => item.dueOff < 0).length
  const weekFollowUps = followUps.filter((item) => item.dueOff >= 0 && item.dueOff <= 7).length
  // 목표는 조직이 회사별로 정해 둔 값의 합이고, 아직 아무도 정하지 않았으면 0 입니다.
  const target = monthlyTotal
  const hasTarget = target > 0
  const month = TODAY.getMonth() + 1
  // 이 달 말일까지 남은 일수. 말일이면 0 이고 ddayLabel 이 '오늘'로 읽습니다.
  const daysLeft = endOfMonth(TODAY).getDate() - TODAY.getDate()
  const percent = hasTarget ? (achieved / target) * 100 : 0
  const over = hasTarget && achieved >= target
  // 목표를 넘기면 트랙이 100%가 아니라 달성률 전체를 담습니다. 그래야 막대가 잘리지 않고
  // 100% 눈금이 트랙 안쪽에 남아 "얼마나 넘었는지"가 길이로 읽힙니다.
  const trackMax = Math.max(percent, 100)
  const surplus = hasTarget ? achieved - target : 0

  return (
    <div className={styles.summary}>
      <button type="button" className={`${styles.kpi} ${styles.jump}`} onClick={onJumpToToday}>
        <span className={styles.top}>
          <span>오늘 방문 회사</span>
        </span>
        <strong className="tnum">{visits}</strong>
        <span className={styles.foot}>
          <small>오늘 일정 {todayList.length}건</small>
          <ArrowDownIcon className={styles.cue} width={14} height={14} />
        </span>
      </button>

      <Tile
        label="미완료 후속업무"
        delta={{ text: `${lateFollowUps} 지연`, tone: 'warn' }}
        value={followUps.length}
        sub={`이번 주 마감 ${weekFollowUps}건`}
        onOpen={() => onOpenList('followUp')}
      />
      <Tile
        label="C/S 대응요청"
        delta={{ text: `긴급 ${urgent}건`, tone: 'danger' }}
        value={requests.length}
        sub={`처리중 ${working}건`}
        onOpen={() => onOpenList('cs')}
      />
      <Tile
        label="계약갱신 예정"
        delta={{ text: '30일 이내', tone: 'warn' }}
        value={renewals.length}
        sub={
          renewals.length === 0
            ? '—'
            : renewals.length === 1
              ? renewals[0].org
              : `${renewals[0].org} 외 ${renewals.length - 1}곳`
        }
        onOpen={() => onOpenList('renewal')}
      />

      {/* 목표 대비 어디쯤인지까지가 이 타일의 몫이고, 무엇이 그 숫자를 만들었는지는
          매출 분석에 있습니다. 그래서 이 타일만 드로어 대신 그 화면으로 넘깁니다. */}
      <Link
        to={ROUTES.SALES}
        className={[styles.goal, over && styles.over].filter(Boolean).join(' ')}
        aria-label={`${month}월 매출 목표${over ? ' — 목표 달성' : ''}. 매출 분석 열기`}
      >
        <div className={styles.goalHead}>
          <span>{month}월 매출 목표</span>
          {over && <i className={styles.delta}>목표 달성</i>}
          <strong className="tnum">{hasTarget ? `${percent.toFixed(1)}%` : '—'}</strong>
        </div>
        {/* 목표가 없으면 견줄 기준이 없습니다. 0을 목표로 적으면 달성률 0%가 부진으로
            읽히므로, 실적 대신 아직 정해지지 않았다는 사실을 그대로 말합니다. */}
        <p className={`${styles.goalValue} tnum`}>
          {hasTarget ? (
            <>
              {won(achieved)} <em>/ {won(target)}</em>
            </>
          ) : (
            <em>목표 미설정</em>
          )}
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
            {surplus > 0 ? `목표 초과 +${won(surplus)}` : `마감 ${ddayLabel(daysLeft)}`}
          </span>
        </div>
      </Link>
    </div>
  )
}
