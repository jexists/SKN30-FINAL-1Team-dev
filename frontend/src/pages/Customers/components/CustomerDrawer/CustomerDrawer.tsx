import type { ReactNode } from 'react'

import { buttonClass } from '@/components/Button'
import Drawer from '@/components/Drawer'
import type { Customer } from '@/types'
import { fmtDay, parseISO } from '@/utils/date'

import styles from './CustomerDrawer.module.scss'

interface Props {
  customer: Customer
  onClose: () => void
}

interface BlockProps {
  title: string
  children: ReactNode
}

function Block({ title, children }: BlockProps) {
  return (
    <section className={styles.block}>
      <h3>{title}</h3>
      {children}
    </section>
  )
}

const shown = (value: string | null | undefined): string => value || '—'

export default function CustomerDrawer({ customer, onClose }: Props) {
  // 담당자가 여럿이면 상세에서는 전부 보여 줍니다. 좁은 표와 달리 자리가 있습니다.
  const ownerNames =
    customer.owners !== undefined && customer.owners.length > 0
      ? customer.owners.map((owner) => owner.name)
      : [customer.owner]

  const facts: [string, string][] = [
    ['부서', shown(customer.dept)],
    ['직함', shown(customer.title)],
    ['담당자', ownerNames.join(', ')],
    ['상태', customer.status],
    ['유입 경로', customer.source],
    ['등록일', fmtDay(parseISO(customer.created))],
  ]

  return (
    <Drawer
      wide
      title={customer.name}
      sub={[customer.org, customer.dept, customer.title].filter(Boolean).join(' · ')}
      resetKey={customer.id}
      onClose={onClose}
      meta={
        <>
          <i
            className={`${styles.pill} ${
              customer.status === '계약'
                ? styles.good
                : customer.status === '보류'
                  ? styles.hold
                  : ''
            }`}
          >
            {customer.status}
          </i>
          <i className={styles.pill}>유입 {customer.source}</i>
          <span className={styles.when}>담당 {customer.owner}</span>
        </>
      }
      footer={
        customer.email ? (
          <a className={buttonClass()} href={`mailto:${customer.email}`}>
            이메일 보내기
          </a>
        ) : undefined
      }
    >
      <div className={styles.grid}>
        <div className={styles.col}>
          <Block title="연락처">
            <dl className={styles.facts}>
              <div>
                <dt>이메일</dt>
                <dd>
                  {customer.email ? (
                    <a className={styles.mail} href={`mailto:${customer.email}`}>
                      {customer.email}
                    </a>
                  ) : (
                    <span className={styles.muted}>등록된 이메일 없음</span>
                  )}
                </dd>
              </div>
              <div>
                <dt>전화</dt>
                <dd>
                  <a className={`${styles.mail} tnum`} href={`tel:${customer.phone}`}>
                    {customer.phone}
                  </a>
                </dd>
              </div>
            </dl>
          </Block>

          <Block title="회사 정보">
            <dl className={styles.facts}>
              <div>
                <dt>회사</dt>
                <dd>{customer.org}</dd>
              </div>
              <div>
                <dt>지역 코드</dt>
                <dd>{shown(customer.regionCode)}</dd>
              </div>
            </dl>
          </Block>
        </div>

        <div className={styles.col}>
          <Block title="고객 정보">
            <dl className={styles.facts}>
              {facts.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </Block>

          <Block title="메모">
            <p className={`${styles.note} ${customer.memo ? '' : styles.muted}`}>
              {customer.memo || '등록된 메모가 없습니다.'}
            </p>
          </Block>
        </div>
      </div>
    </Drawer>
  )
}
