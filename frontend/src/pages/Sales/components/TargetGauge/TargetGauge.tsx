// 오른쪽 패널. 이 기간 매출이 목표선까지 얼마나 왔는지 한 줄로 보여 줍니다.
//
// 막대는 항상 회사별입니다. 왼쪽 표의 탭을 따라가지 않습니다. 목표선과 견주는 기준이
// 화면 안에서 두 가지가 되면 "몇 % 남았나"를 읽는 자리가 흔들리기 때문입니다.
import { Bar, BarChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { TODAY_ISO } from '@/utils/date'
import { won, wonFull } from '@/utils/format'

import type { Range } from '../../periods'
import { pct, type SalesSummary } from '../../useSalesSummary'

import styles from './TargetGauge.module.scss'

/** 계열 색. global.scss 의 토큰을 그대로 씁니다. 마지막 하나는 '기타' 몫입니다. */
const COLORS = [
  'var(--blue)',
  'var(--green)',
  'var(--orange)',
  'var(--purple)',
  'var(--red)',
  'var(--muted-2)',
]

const TOP = COLORS.length - 1

interface Slice {
  name: string
  value: number
  color: string
}

/** 상위 5개 회사 + 기타. 계열이 색보다 많아지면 색이 겹쳐 읽을 수 없게 됩니다. */
function toSlices(summary: SalesSummary): Slice[] {
  const scored = summary.groups.filter((g) => g.actual > 0)
  const head = scored
    .slice(0, TOP)
    .map((g, i) => ({ name: g.key, value: g.actual, color: COLORS[i] }))
  const rest = scored.slice(TOP).reduce((sum, g) => sum + g.actual, 0)

  return rest > 0 ? [...head, { name: '기타', value: rest, color: COLORS[TOP] }] : head
}

export default function TargetGauge({ range, summary }: { range: Range; summary: SalesSummary }) {
  const { totals, delta, prevActual } = summary
  const slices = toSlices(summary)
  // 목표가 없으면 gap 이 0 이라 '목표 초과'가 참이 되어 버립니다. 아무도 목표를 정하지
  // 않은 첫 세팅에서 목표를 넘겼다고 말하지 않게 목표 유무를 먼저 봅니다.
  const hasTarget = totals.target > 0
  const over = hasTarget && totals.gap <= 0
  // 목표는 기간 전체를 덮습니다. 아직 끝나지 않은 기간이면 달성률이 낮게 나오는 것이
  // 정상이므로 그 사실을 적어 둡니다. 이 표시가 없으면 진행 중인 분기가 부진해 보입니다.
  const ongoing = range.toISO >= TODAY_ISO

  // 목표선이 막대 끝에 딱 붙어 잘리지 않게 축을 조금 더 길게 잡습니다.
  const axisMax = Math.max(totals.actual, totals.target) * 1.08 || 1
  // 한 줄짜리 누적 막대입니다. name 이 있어야 세로축이 칸 하나를 잡고 막대가 그려집니다.
  const row = { name: '실적', ...Object.fromEntries(slices.map((s) => [s.name, s.value])) }

  return (
    <section className={styles.panel} aria-label="목표 대비 매출">
      <header className={styles.head}>
        <p className={styles.caption}>{range.label} 매출</p>
        <p className={styles.value}>
          <strong className="tnum">{won(totals.actual)}</strong>
          <span className="tnum">
            {hasTarget ? `/ 목표 ${won(totals.target)}` : '/ 목표 미설정'}
          </span>
        </p>
        {hasTarget && (
          <p className={styles.rate}>
            <b className={`tnum ${over ? 'positive' : ''}`}>{totals.rate.toFixed(1)}%</b>
            <span className={over ? 'positive' : 'danger'}>
              {over ? `목표 초과 ${won(-totals.gap)}` : `목표까지 ${won(totals.gap)} 부족`}
            </span>
            {ongoing && <em className={styles.ongoing}>기간 진행 중</em>}
          </p>
        )}
      </header>

      {totals.actual === 0 ? (
        <p className={styles.empty}>이 기간에 확정된 매출이 없습니다.</p>
      ) : (
        <div className={styles.chart}>
          <ResponsiveContainer width="100%" height={104}>
            {/* 목표선 라벨이 막대 위에 붙으므로 위쪽 여백을 비워 둡니다. */}
            <BarChart
              data={[row]}
              layout="vertical"
              margin={{ top: 26, right: 12, bottom: 0, left: 4 }}
            >
              {/* 축 눈금은 두지 않습니다. 실적·목표 금액은 이미 위에 적혀 있고,
                  여기서 읽을 것은 막대가 목표선까지 얼마나 왔는지 하나뿐입니다. */}
              <XAxis type="number" domain={[0, axisMax]} hide />
              <YAxis type="category" dataKey="name" hide />
              <Tooltip
                cursor={false}
                formatter={(value, name) => [wonFull(Number(value)), String(name)]}
                contentStyle={{
                  borderRadius: 10,
                  border: '1px solid var(--line)',
                  boxShadow: 'var(--sh-2)',
                  fontSize: 12,
                }}
              />

              {slices.map((s) => (
                <Bar key={s.name} dataKey={s.name} stackId="actual" fill={s.color} barSize={44} />
              ))}

              {hasTarget && (
                <ReferenceLine
                  x={totals.target}
                  stroke="var(--ink)"
                  strokeDasharray="5 4"
                  strokeWidth={2}
                  label={{
                    value: `목표 ${won(totals.target)}`,
                    position: 'top',
                    fontSize: 11,
                    fontWeight: 600,
                    fill: 'var(--ink)',
                  }}
                />
              )}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <ul className={styles.legend}>
        {slices.map((s) => (
          <li key={s.name}>
            <i style={{ background: s.color }} />
            <span>{s.name}</span>
            <b className="tnum">{pct(s.value, totals.actual).toFixed(1)}%</b>
          </li>
        ))}
      </ul>

      <p className={styles.delta}>
        직전 기간 대비{' '}
        <b className={`tnum ${delta >= 0 ? 'positive' : 'danger'}`}>
          {delta >= 0 ? '+' : '−'}
          {won(Math.abs(delta))}
        </b>
        <span className="tnum">(직전 {won(prevActual)})</span>
      </p>
    </section>
  )
}
