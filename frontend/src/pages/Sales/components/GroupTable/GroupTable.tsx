// 왼쪽 패널. 계약을 회사별 또는 지역별로 접어 보여 주고, 행을 펼치면 계약건이 나옵니다.
//
// 탭은 무엇으로 묶을지만 정합니다. 어느 탭이든 합계 행의 건수와 금액은 같습니다.
import { useState } from 'react'

import { ChevronDownIcon } from '@/components/icons'
import OwnerName from '@/components/OwnerName'
import Tabs from '@/components/Tabs'
import type { SalesDeal } from '@/pages/Deals/useSalesDeals'
import { fmtDotShort, parseISO } from '@/utils/date'
import { wonFull } from '@/utils/format'

import { GROUP_BYS, GROUP_HEADER, GROUP_LABEL, type GroupBy } from '../../periods'
import { colorOf } from '../../slices'
import type { SalesGroup, SalesSummary } from '../../useSalesSummary'

import styles from './GroupTable.module.scss'

interface GroupTableProps {
  by: GroupBy
  onByChange: (next: GroupBy) => void
  onSelectGroup: (key: string) => void
  selectedGroupKey: string | null
  summary: SalesSummary
}

/** 확정이 아닌 계약만 배지를 답니다. 확정에 배지를 달면 목록이 배지로 가득 찹니다. */
function StatusBadge({ status }: { status: SalesDeal['status'] }) {
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
            <small className={styles.dealMeta}>
              {c.kind}
              <OwnerName name={c.owner} memberId={c.ownerMemberId} />
            </small>
          </span>
          <StatusBadge status={c.status} />
          <span className={`${styles.dealDate} tnum`}>{fmtDotShort(parseISO(c.date))}</span>
          {/* 위의 합계와 같은 값을 세야 하므로 예상금액이 아니라 계약금액을 적습니다. */}
          <span className={`${styles.dealAmount} tnum ${c.status === '확정' ? '' : styles.faded}`}>
            {c.contractAmount === null ? '-' : wonFull(c.contractAmount)}
          </span>
        </li>
      ))}
    </ul>
  )
}

export default function GroupTable({
  by,
  onByChange,
  onSelectGroup,
  selectedGroupKey,
  summary,
}: GroupTableProps) {
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
        <Tabs
          variant="segmented"
          size="sm"
          items={GROUP_BYS.map((item) => ({ value: item, label: GROUP_LABEL[item] }))}
          value={by}
          label="계약 묶는 기준"
          onChange={switchBy}
        />
      </header>

      <div className={styles.columns}>
        <span>{GROUP_HEADER[by]}</span>
        <span>건수</span>
        <span>계약금액</span>
        <span>비중</span>
      </div>

      <ul className={styles.rows}>
        {/* 묶을 것이 하나도 없으면 머리글과 합계만 남아 표가 고장난 것처럼 보입니다. */}
        {groups.length === 0 && <li className={styles.none}>이 기간에 등록된 계약이 없습니다.</li>}
        {groups.map((group, index) => {
          const open = openKeys.has(group.key)
          // 오른쪽 패널과 같은 규칙으로 색을 뽑습니다. 한 줄과 한 조각이 같은 색이어야
          // 두 패널을 눈으로 이을 수 있습니다.
          const color = colorOf(index, group.actual)
          const selected = group.key === selectedGroupKey

          return (
            <li key={group.key}>
              <div className={`${styles.row} ${selected ? styles.isSelected : ''}`}>
                <span className={styles.nameCell}>
                  <button
                    type="button"
                    className={styles.groupSelect}
                    aria-pressed={selected}
                    onClick={() => onSelectGroup(group.key)}
                  >
                    <i className={styles.swatch} style={{ background: color }} />
                    {group.key}
                  </button>
                  <button
                    type="button"
                    className={`${styles.disclosure} ${open ? styles.isOpen : ''}`}
                    aria-expanded={open}
                    aria-label={`${group.key} 계약 ${open ? '접기' : '펼치기'}`}
                    onClick={() => toggle(group.key)}
                  >
                    <ChevronDownIcon className={styles.caret} width={14} height={14} />
                  </button>
                </span>
                <span className={`${styles.count} tnum`}>{group.contracts.length}건</span>
                <span className={`${styles.amount} tnum`}>{wonFull(group.actual)}</span>
                <span className={`${styles.share} tnum`}>
                  {group.share.toFixed(1)}%
                  <i style={{ background: color, transform: `scaleX(${group.share / 100})` }} />
                </span>
              </div>

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

      {/* <p className={styles.note}>
        계약금액은 확정 계약만 더합니다. 진행중·취소 건은 목록에만 남습니다.
      </p> */}
    </section>
  )
}
