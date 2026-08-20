import { Link } from 'react-router'

import { ArrowDownIcon } from '@/components/icons'
import { ROUTES } from '@/constants/routes'
import type { SalesDeal } from '@/pages/Deals/useSalesDeals'
import { agendaFor, useAgenda } from '@/shared/agenda'
import type { SupportRequestResponse } from '@/types'
import { addDays, endOfMonth, iso, startOfMonth, TODAY, TODAY_ISO } from '@/utils/date'
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
  const month = TODAY.getMonth() + 1

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
        delta={{ text: 'API 필요', tone: 'warn' }}
        value="—"
        sub="후속업무 조회 계약 없음"
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

      <Link
        to={ROUTES.SALES}
        className={styles.goal}
        aria-label={`${month}월 확정 매출. 매출 분석 열기`}
      >
        <div className={styles.goalHead}>
          <span>{month}월 확정 매출</span>
          <strong className="tnum">목표 API 없음</strong>
        </div>
        <p className={`${styles.goalValue} tnum`}>
          {won(achieved)} <em>/ 목표 미연결</em>
        </p>
        <div className={styles.goalFoot}>
          <span>영업딜 API 기준</span>
          <span>계약 목표 조회 계약 필요</span>
        </div>
      </Link>
    </div>
  )
}
