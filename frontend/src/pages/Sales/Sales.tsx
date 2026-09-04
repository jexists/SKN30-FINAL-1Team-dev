// 매출 분석 한 화면. 위에 기간 줄, 아래 좌우 두 칸입니다.
// 왼쪽은 계약을 회사별·지역별로 접은 리스트, 오른쪽은 목표선과 견준 이 기간 매출입니다.
import { useSearchParams } from 'react-router'

import ErrorToast from '@/components/ErrorToast'
import Skeleton from '@/components/Skeleton'
import useSalesDeals from '@/pages/Deals/useSalesDeals'

import { downloadCsv, toCsv } from '@/utils/csv'

import GroupTable from './components/GroupTable'
import PeriodBar from './components/PeriodBar'
import TargetGauge from './components/TargetGauge'
import {
  GROUP_HEADER,
  GROUP_LABEL,
  hasTarget,
  resolveRange,
  toGroupBy,
  toOffset,
  toPeriodType,
  type GroupBy,
  type PeriodType,
} from './periods'
import useSalesSummary from './useSalesSummary'

import styles from './Sales.module.scss'

export default function Sales() {
  const [params, setParams] = useSearchParams()
  const type = toPeriodType(params.get('tab'))
  const offset = toOffset(params.get('o'))
  const by = toGroupBy(params.get('by'))

  const range = resolveRange(type, offset)

  const { cards, loading, error, reload } = useSalesDeals(null, null, 'list')
  // 왼쪽 표는 탭이 고른 축으로, 오른쪽 패널은 언제나 회사별로 봅니다.
  const grouped = useSalesSummary(cards, type, offset, by)
  const byOrg = useSalesSummary(cards, type, offset, 'org')

  /** 기간 탭을 바꾸면 이동량은 의미가 달라지므로 현재 기간으로 되돌립니다. */
  const setType = (next: PeriodType) => {
    const query = new URLSearchParams(params)
    query.set('tab', next)
    query.delete('o')
    setParams(query)
  }

  const setParam = (key: string, value: string, isDefault: boolean) => {
    const query = new URLSearchParams(params)
    if (isDefault) query.delete(key)
    else query.set(key, value)
    setParams(query)
  }

  const exportCsv = () => {
    // 상품에는 목표가 없습니다. 빈 목표를 0으로 내보내면 달성률 0% 로 읽힙니다.
    const withTarget = hasTarget(by)
    const headers = [
      GROUP_HEADER[by],
      '건수',
      '계약금액',
      ...(withTarget ? ['목표금액', '달성률(%)'] : []),
      '비중(%)',
    ]
    const rows = grouped.groups.map((g) => [
      g.key,
      String(g.contracts.length),
      String(g.actual),
      ...(withTarget ? [String(g.target), g.rate.toFixed(1)] : []),
      g.share.toFixed(1),
    ])
    rows.push([
      '합계',
      String(grouped.totals.count),
      String(grouped.totals.actual),
      ...(withTarget ? [String(grouped.totals.target), grouped.totals.rate.toFixed(1)] : []),
      '100.0',
    ])

    downloadCsv(`매출분석_${range.label}_${GROUP_LABEL[by]}.csv`, toCsv(headers, rows))
  }

  // 첫 진입입니다. 기간 줄과 좌우 두 칸이 따로 나타나면 화면이 두 번 들썩이므로
  // 한 장을 통째로 자리표시자로 두고 다 받은 뒤 한 번에 바꿉니다.
  if (loading && cards.length === 0 && !error) {
    return (
      <section aria-busy>
        <h1 className="sr-only">매출 분석</h1>
        <Skeleton className={styles.periodSkeleton} height={36} radius="var(--r-sm)" />
        <div className={styles.split}>
          <Skeleton height={480} radius="var(--r-lg)" />
          <Skeleton height={360} radius="var(--r-lg)" />
        </div>
      </section>
    )
  }

  return (
    <section>
      {/* Topbar 빵부스러기가 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
      <h1 className="sr-only">매출 분석</h1>

      <PeriodBar
        type={type}
        offset={offset}
        range={range}
        onTypeChange={setType}
        onOffsetChange={(next) => setParam('o', String(next), next === 0)}
        onExport={exportCsv}
      />

      <ErrorToast message={error} onRetry={reload} />

      {!error && loading ? (
        <div className={styles.split} role="status">
          <span className="sr-only">매출 데이터를 새로고침하는 중입니다.</span>
          <Skeleton height={480} radius="var(--r-lg)" />
          <Skeleton height={360} radius="var(--r-lg)" />
        </div>
      ) : (
        <div className={styles.split}>
          <GroupTable
            by={by}
            onByChange={(next: GroupBy) => setParam('by', next, next === 'org')}
            summary={grouped}
          />
          <TargetGauge range={range} summary={byOrg} />
        </div>
      )}
    </section>
  )
}
