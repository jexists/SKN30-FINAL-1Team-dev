// 왼쪽 패널. 계약을 회사별 또는 지역별로 접어 보여 주고, 행을 펼치면 계약건이 나옵니다.
//
// 탭은 무엇으로 묶을지만 정합니다. 어느 탭이든 합계 행의 건수와 금액은 같습니다.
import { useState } from 'react'

import { ChevronDownIcon } from '@/components/icons'
import type { Contract } from '@/types'
import { fmtDotShort, parseISO } from '@/utils/date'
import { wonFull } from '@/utils/format'

import { GROUP_BYS, GROUP_HEADER, GROUP_LABEL, type GroupBy } from '../../periods'
import type { SalesGroup, SalesSummary } from '../../useSalesSummary'

import styles from './GroupTable.module.scss'

interface GroupTableProps {
  by: GroupBy
  onByChange: (next: GroupBy) => void
  summary: SalesSummary
}

/** 확정이 아닌 계약만 배지를 답니다. 확정에 배지를 달면 목록이 배지로 가득 찹니다. */
function StatusBadge({ status }: { status: Contract['status'] }) {
  if (status === '확정') return null
  return (
    <i className={`${styles.badge} ${status === '취소' ? styles.isCanceled : styles.isPending}`}>
      {status}
    </i>
  )
}

function ContractRows({ group, by }: { group: SalesGroup; by: GroupBy }) {
  if (group.contracts.length === 0) {
    return <p className={styles.none}>이 기간에 등록된 계약이 없습니다.</p>
  }

  return (
    <ul className={styles.deals}>
      {group.contracts.map((c) => (
        <li key={c.no} className={styles.deal}>
          <span className={`${styles.no} tnum`}>{c.no}</span>
          {/* 그룹 이름과 같은 값을 한 줄 안에서 두 번 말하지 않습니다. */}
          <span className={styles.product}>
            {by === 'product' ? c.org : c.product}
            <small>
              {c.kind} · {c.owner}
            </small>
          </span>
          <StatusBadge status={c.status} />
          <span className={`${styles.dealDate} tnum`}>{fmtDotShort(parseISO(c.date))}</span>
          <span className={`${styles.dealAmount} tnum ${c.status === '확정' ? '' : styles.faded}`}>
            {wonFull(c.amount)}
          </span>
        </li>
      ))}
    </ul>
  )
}

export default function GroupTable({ by, onByChange, summary }: GroupTableProps) {
  // 회사 키와 지역 키가 섞이지 않게 탭을 바꾸면 펼침을 접습니다.
  const [openKeys, setOpenKeys] = useState<Set<string>>(new Set())

  const toggle = (key: string) => {
    const next = new Set(openKeys)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setOpenKeys(next)
  }

  const switchBy = (next: GroupBy) => {
    setOpenKeys(new Set())
    onByChange(next)
  }

  const { groups, totals } = summary

  return (
    <section className={styles.panel} aria-label="계약 리스트">
      <header className={styles.head}>
        <h2 className={styles.title}>계약 리스트</h2>
        <div className={styles.tabs} role="tablist" aria-label="계약 묶는 기준">
          {GROUP_BYS.map((item) => (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={by === item}
              className={`${styles.tab} ${by === item ? styles.isActive : ''}`}
              onClick={() => switchBy(item)}
            >
              {GROUP_LABEL[item]}
            </button>
          ))}
        </div>
      </header>

      <div className={styles.columns}>
        <span>{GROUP_HEADER[by]}</span>
        <span>건수</span>
        <span>계약금액</span>
        <span>비중</span>
      </div>

      <ul className={styles.rows}>
        {groups.map((group) => {
          const open = openKeys.has(group.key)

          return (
            <li key={group.key}>
              <button
                type="button"
                className={`${styles.row} ${open ? styles.isOpen : ''}`}
                aria-expanded={open}
                onClick={() => toggle(group.key)}
              >
                <span className={styles.name}>
                  <ChevronDownIcon className={styles.caret} width={14} height={14} />
                  {group.key}
                </span>
                <span className={`${styles.count} tnum`}>{group.contracts.length}건</span>
                <span className={`${styles.amount} tnum`}>{wonFull(group.actual)}</span>
                <span className={`${styles.share} tnum`}>{group.share.toFixed(1)}%</span>
              </button>

              {open && <ContractRows group={group} by={by} />}
            </li>
          )
        })}
      </ul>

      <div className={styles.total}>
        <span>합계</span>
        <span className="tnum">{totals.count}건</span>
        <span className="tnum">{wonFull(totals.actual)}</span>
        <span className="tnum">100.0%</span>
      </div>

      <p className={styles.note}>
        계약금액은 확정 계약만 더합니다. 진행중·취소 건은 목록에만 남습니다.
      </p>
    </section>
  )
}
