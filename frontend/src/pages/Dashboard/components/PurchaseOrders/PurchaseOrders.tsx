import { Link } from 'react-router'

import { activeOrders, dday, isLate, orderItemLabel } from '@/content/orders'
import type { PurchaseOrder } from '@/content/types'
import { ROUTES } from '@/constants/routes'
import { addDays, fmtDay, parseISO, TODAY } from '@/utils/date'

import styles from './PurchaseOrders.module.scss'

// 다섯 조건은 서로 겹칩니다(한 발주가 진행중이면서 납기 지연일 수 있습니다).
// 그래서 단계 표시가 아니라 나란한 타일입니다 — 연결선은 순서를 암시합니다.
const FILTERS: {
  key: string
  label: string
  note: () => string
  alert?: boolean
  test: (o: PurchaseOrder) => boolean
}[] = [
  {
    key: 'pending',
    label: '승인 대기',
    note: () => '팀장 승인 필요',
    test: (o) => o.status === '승인대기',
  },
  {
    key: 'request',
    label: '출고의뢰서 처리',
    note: () => '출고 준비 단계',
    test: (o) => o.status === '출고의뢰서 작성완료',
  },
  {
    key: 'inflight',
    label: '생산·출고 진행중',
    note: () => '승인부터 출고까지',
    test: (o) => ['승인', '출고의뢰서 작성완료', '생산중', '출고'].includes(o.status),
  },
  {
    key: 'thisweek',
    label: '이번 주 입고 예정',
    note: () => `${fmtDay(TODAY).slice(0, -4)} – ${fmtDay(addDays(TODAY, 7)).slice(0, -4)}`,
    test: (o) => o.status !== '입고완료' && dday(o) >= 0 && dday(o) <= 7,
  },
  {
    key: 'late',
    label: '납기 지연',
    note: () => '예상 입고일이 납기 초과',
    alert: true,
    test: isLate,
  },
]

export default function PurchaseOrders() {
  const active = activeOrders()
  const late = active.filter(isLate)

  return (
    <article className={styles.po}>
      <div className={styles.head}>
        <div>
          <p className="eyebrow">Purchase order</p>
          <h2>발주 진행 현황</h2>
        </div>
        <Link className={styles.link} to={ROUTES.ORDERS}>
          발주관리 전체 →
        </Link>
      </div>

      <div className={styles.strip}>
        {FILTERS.map((f) => {
          const n = active.filter(f.test).length
          const cls = [styles.stat, n === 0 && styles.isZero, f.alert && n > 0 && styles.isAlert]
            .filter(Boolean)
            .join(' ')
          return (
            <div key={f.key} className={cls}>
              <span className={styles.label}>{f.label}</span>
              <strong className="tnum">{n}</strong>
              <small>{f.note()}</small>
            </div>
          )
        })}
      </div>

      {late.length === 0 ? (
        <div className={styles.clear}>
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M20 6L9 17l-5-5" />
          </svg>
          납기를 넘긴 발주가 없습니다.
        </div>
      ) : (
        late.map((o) => {
          const over = o.expectOff - o.dueOff
          const due = parseISO(o.due)
          const expect = parseISO(o.expect)
          return (
            <div key={o.no} className={styles.alert}>
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M12 9v4M12 17v.01" />
                <path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
              </svg>
              <span>
                <strong>
                  {o.hospital} · {orderItemLabel(o)}
                </strong>
                <br />
                예상 입고 {expect.getMonth() + 1}/{expect.getDate()} — 납기 {due.getMonth() + 1}/
                {due.getDate()} 대비 {over}일 초과
              </span>
            </div>
          )
        })
      )}
    </article>
  )
}
