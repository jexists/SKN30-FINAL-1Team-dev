// 표 셀의 표시 전용 조각들. columns.ts 가 값(정렬·검색·CSV)을 맡고
// 여기가 보이는 모양만 맡습니다.
import { relativeDayLabel } from '@/content/customers'
import type { Customer } from '@/content/types'
import { fmtDotShort, parseISO } from '@/utils/date'

import styles from './Customers.module.scss'

export function NameCell({ customer }: { customer: Customer }) {
  return (
    <span className={styles.nameCell}>
      <span className={styles.avatar} aria-hidden="true">
        {customer.name.slice(0, 1)}
      </span>
      <span className={styles.nameText}>{customer.name}</span>
    </span>
  )
}

export function EmailCell({ email }: { email: string }) {
  return (
    <a className={styles.linkCell} href={`mailto:${email}`}>
      {email}
    </a>
  )
}

export function PlainNumber({ value }: { value: string }) {
  return <span className="tnum">{value}</span>
}

export function DateCell({ date }: { date: string }) {
  return (
    <span className={styles.dateCell}>
      <span className="tnum">{fmtDotShort(parseISO(date))}</span>
      <span className={styles.dateRel}>{relativeDayLabel(date)}</span>
    </span>
  )
}

export function StatusCell({ customer }: { customer: Customer }) {
  return (
    <span
      className={[
        styles.badge,
        customer.status === '계약' && styles.badgeWon,
        customer.status === '보류' && styles.badgeHold,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {customer.status}
    </span>
  )
}

/** 표에서 색이 붙는 유일한 자리입니다. 색 = 후속이 늦었다는 뜻. */
export function NextCell({ customer }: { customer: Customer }) {
  if (customer.next === null) return <span className={styles.overdue}>일정 없음</span>

  if (customer.overdue) {
    return (
      <span className={styles.overdue}>
        {fmtDotShort(parseISO(customer.next))} · {relativeDayLabel(customer.next)}
      </span>
    )
  }

  return <DateCell date={customer.next} />
}
