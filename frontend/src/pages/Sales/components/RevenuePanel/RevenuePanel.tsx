// 오른쪽 패널. 이 기간 매출이 얼마고, 어떻게 흘러왔고, 누가 끌었는지 순서로 읽습니다.
//
// 왼쪽 표의 탭(회사별·지역별·상품별)을 그대로 따라갑니다. 같은 화면에서 왼쪽은
// 지역을 말하는데 오른쪽만 회사를 말하면, 색이 같은 줄이 서로 다른 것을 가리킵니다.
import Button from '@/components/Button'
import { useOwnerColor } from '@/shared/ownerColors'
import { won, wonFull } from '@/utils/format'

import { GROUP_LABEL, type GroupBy, type Range } from '../../periods'
import { REST_COLOR, toSlices, type Slice } from '../../slices'
import { pct, type OwnerShare, type SalesGroup, type SalesSummary } from '../../useSalesSummary'
import type { TrendPoint } from '../../useSalesTrend'

import styles from './RevenuePanel.module.scss'

interface RevenuePanelProps {
  range: Range
  summary: SalesSummary
  by: GroupBy
  onSelectGroup: (key: string | null) => void
  selectedGroup: SalesGroup | null
  trend: TrendPoint[]
  trendCaption: string
}

/**
 * 기간마다 하나씩 세운 막대.
 *
 * 선으로 그리면 칸과 칸 사이를 이어 붙여 "쭉 이어지는 흐름"이라고 말하게 됩니다.
 * 여기서 견주는 것은 서로 떨어진 몇 개의 기간이고, 매출이 없던 기간은 바닥에
 * 그은 줄이 아니라 막대가 없는 것으로 읽혀야 합니다.
 */
function TrendBars({ points, caption }: { points: TrendPoint[]; caption: string }) {
  const max = Math.max(...points.map((p) => p.actual))
  const summary = points.map((p) => `${p.label} ${won(p.actual)}`).join(', ')

  return (
    <figure className={styles.trend}>
      <figcaption className={styles.trendCaption}>{caption}</figcaption>

      {/* 막대 자체는 그림입니다. 읽어 주는 것은 위의 요약 한 줄로 충분합니다. */}
      <ul className={styles.bars} role="img" aria-label={`${caption} 매출. ${summary}.`}>
        {points.map((p, i) => (
          <li
            key={p.offset}
            className={p.isCurrent ? styles.isNow : undefined}
            title={`${p.label} · ${wonFull(p.actual)}`}
          >
            <span className={styles.barTrack}>
              <b
                className={p.actual > 0 ? undefined : styles.isZero}
                style={{
                  height: `${max > 0 ? (p.actual / max) * 100 : 0}%`,
                  animationDelay: `${i * 45}ms`,
                }}
              />
            </span>
            <span className={styles.barLabel}>{p.short}</span>
          </li>
        ))}
      </ul>
    </figure>
  )
}

/**
 * 담당자 한 줄. 색은 계열 팔레트가 아니라 팀장이 그 사람에게 준 색입니다.
 *
 * 순위마다 색을 새로 뽑으면 이번 달 1등과 지난달 1등이 같은 색이 되어, 다른 화면의
 * 이름표 색과 뜻이 어긋납니다. 색을 아직 안 받은 사람은 회색으로 물러섭니다.
 */
function OwnerRank({ share, top, total }: { share: OwnerShare; top: number; total: number }) {
  const color = useOwnerColor(share.memberId) ?? REST_COLOR

  return (
    <li className={styles.rankStatic}>
      <i style={{ background: color }} />
      <span className={styles.rankName}>
        <b>{share.name}</b>
        <small>계약 {share.count}건</small>
      </span>
      <span className={styles.rankBar}>
        <b
          style={{ background: color, transform: `scaleX(${top > 0 ? share.actual / top : 0})` }}
        />
      </span>
      <span className={`${styles.rankAmount} tnum`}>{won(share.actual)}</span>
      <span className={`${styles.rankShare} tnum`}>{pct(share.actual, total).toFixed(1)}%</span>
    </li>
  )
}

function GroupRank({
  slice,
  top,
  total,
  selected,
  onSelect,
}: {
  slice: Slice
  top: number
  total: number
  selected: boolean
  onSelect: (() => void) | undefined
}) {
  const selectable = onSelect !== undefined

  return (
    <li>
      <button
        type="button"
        className={`${styles.rankButton} ${selected ? styles.isSelected : ''}`}
        aria-pressed={selectable ? selected : undefined}
        aria-label={
          selectable
            ? `${slice.key} 담당자별 매출 보기`
            : `${slice.key}는 개별 항목으로 나눠 볼 수 없습니다`
        }
        disabled={!selectable}
        onClick={onSelect}
      >
        <i style={{ background: slice.color }} />
        <span className={styles.rankName}>{slice.key}</span>
        <span className={styles.rankBar}>
          <b style={{ background: slice.color, transform: `scaleX(${slice.value / top})` }} />
        </span>
        <span className={`${styles.rankAmount} tnum`}>{won(slice.value)}</span>
        <span className={`${styles.rankShare} tnum`}>{pct(slice.value, total).toFixed(1)}%</span>
      </button>
    </li>
  )
}

/**
 * 선택한 회사·지역·상품이 어떤 담당자 실적으로 구성됐는지 보여 줍니다.
 */
function OwnerRanks({ owners, total }: { owners: OwnerShare[]; total: number }) {
  const top = Math.max(...owners.map((share) => share.actual), 0)

  return (
    <div className={styles.owners}>
      <p className={styles.ownersCaption}>담당자별</p>
      <ul className={styles.ranks}>
        {owners.map((share) => (
          <OwnerRank key={share.memberId} share={share} top={top} total={total} />
        ))}
      </ul>
    </div>
  )
}

export default function RevenuePanel({
  range,
  summary,
  by,
  onSelectGroup,
  selectedGroup,
  trend,
  trendCaption,
}: RevenuePanelProps) {
  const { totals, delta, prevActual } = summary
  const slices = toSlices(summary.groups)
  // 순위 막대는 제일 큰 몫을 꽉 채웁니다. 합계 대비로 그리면 상위 몇 곳만 보이고
  // 나머지는 실오라기가 되어, 4등과 5등의 차이를 눈으로 못 잡습니다.
  //
  // 첫 줄이 아니라 최댓값으로 나눕니다. '기타'는 여러 몫을 합친 값이라 1등 한 곳보다
  // 클 수 있고, 그러면 막대가 1을 넘어 옆 금액 위로 넘쳐 흐릅니다.
  const top = Math.max(...slices.map((s) => s.value), 0)
  const trendMax = Math.max(...trend.map((p) => p.actual))
  const up = delta >= 0

  return (
    <section className={styles.panel} aria-label="기간 매출">
      <header className={styles.head}>
        <p className={styles.caption}>
          {range.label} · {GROUP_LABEL[by]}
        </p>

        <div className={styles.headline}>
          <strong className="tnum">{won(totals.actual)}</strong>
          {prevActual > 0 && (
            <span className={`${styles.delta} ${up ? styles.isUp : styles.isDown} tnum`}>
              {up ? '▲' : '▼'} {won(Math.abs(delta))}
            </span>
          )}
        </div>

        <p className={styles.sub}>
          <span className="tnum">직전 {won(prevActual)}</span>
          <span className="tnum">계약 {totals.count}건</span>
          {/* 목표가 들어오면 달성률이 여기 붙습니다. 아직 아무도 목표를 정하지 않았고,
              정한 적 없는 값의 부재를 화면에서 가장 좋은 자리로 알릴 이유는 없습니다. */}
          {totals.target > 0 && <span className="tnum">목표 대비 {totals.rate.toFixed(1)}%</span>}
        </p>
      </header>

      {totals.actual === 0 ? (
        <p className={styles.empty}>이 기간에 확정된 매출이 없습니다.</p>
      ) : (
        // 리본과 순위 줄은 같은 것을 두 가지로 말합니다. 한 덩어리로 묶어 아래의
        // 추세와 갈라 놓아야, 어느 쪽에 붙은 그림인지 헷갈리지 않습니다.
        <div className={styles.mix}>
          {/* 구성 리본. 이름은 아래 순위 줄이 이미 말하므로 범례를 따로 두지 않습니다. */}
          <div className={styles.ribbon} role="group" aria-label={`${GROUP_LABEL[by]}별 매출 구성`}>
            {slices.map((s) => (
              <button
                key={s.key}
                type="button"
                className={styles.ribbonSlice}
                aria-label={
                  s.count === 1
                    ? `${s.key} 담당자별 매출 보기`
                    : `${s.key}는 개별 항목으로 나눠 볼 수 없습니다`
                }
                disabled={s.count !== 1}
                style={{ flexGrow: s.value, background: s.color }}
                onClick={s.count === 1 ? () => onSelectGroup(s.key) : undefined}
              />
            ))}
          </div>

          <ul className={styles.ranks}>
            {slices.map((s) => (
              <GroupRank
                key={s.key}
                slice={s}
                top={top}
                total={totals.actual}
                selected={selectedGroup?.key === s.key}
                onSelect={s.count === 1 ? () => onSelectGroup(s.key) : undefined}
              />
            ))}
          </ul>
        </div>
      )}

      {/* 이 기간을 먼저 읽고, 그 다음에 지난 기간과 견줍니다. 이 기간이 0원이어도
          막대는 남깁니다. 비어 있다는 사실이야말로 앞뒤와 견줘야 읽기 때문입니다. */}
      {trendMax > 0 && <TrendBars points={trend} caption={trendCaption} />}

      {/* 전체 비교를 유지한 채, 고른 항목이 어떤 담당자 실적으로 만들어졌는지 아래에
          붙입니다. 차트를 갈아 끼우면 비교 기준을 잃으므로 상세는 보완 정보입니다. */}
      {selectedGroup !== null && (
        <section className={styles.breakdown} aria-labelledby="selected-group-breakdown">
          <div className={styles.breakdownHead}>
            <div>
              <h3 id="selected-group-breakdown">{selectedGroup.key} 매출 구성</h3>
              <p>
                계약 {selectedGroup.contracts.length}건 · 담당자 {selectedGroup.owners.length}명
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={() => onSelectGroup(null)}>
              상세 닫기
            </Button>
          </div>

          {selectedGroup.actual === 0 ? (
            <p className={styles.empty}>이 항목에는 확정된 매출이 없습니다.</p>
          ) : (
            <OwnerRanks owners={selectedGroup.owners} total={selectedGroup.actual} />
          )}
        </section>
      )}
    </section>
  )
}
