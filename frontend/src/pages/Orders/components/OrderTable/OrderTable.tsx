// 발주 목록 표입니다. 줄 하나가 발주 한 건이고, 누르면 오른쪽 드로어가 섭니다.
//
// 계약 목록 표와 같은 구조입니다. 다른 점은 예상 입고 칸으로, 납기를 넘긴 건은
// 여기서 바로 알아야 해서 지연 일수를 함께 붙입니다.
import { useMemo } from 'react'

import Button from '@/components/Button'
import { ArrowUpIcon, OrdersIcon, SearchIcon, SortIcon } from '@/components/icons'
import { BP_DESKTOP } from '@/constants/breakpoints'
import { isLate, orderItemLabel, orderTotal } from '@/shared/orders'
import type { PurchaseOrder } from '@/types'
import useMediaQuery from '@/hooks/useMediaQuery'
import { useOwnerScope } from '@/scope/scopeContext'
import { fmtDotShort, parseISO } from '@/utils/date'
import { won } from '@/utils/format'

import { ORDER_COLUMNS, type SortState } from '../../columns'
import { TONE_OF } from '../../pipeline'

import styles from './OrderTable.module.scss'

interface Props {
  rows: PurchaseOrder[]
  sort: SortState
  onSort: (id: string) => void
  onOpen: (no: string) => void
  isFiltered: boolean
  onClearFilters: () => void
  onCreate: () => void
}

/** 납기를 며칠 넘겼는지. 표와 카드가 같은 문구를 씁니다. */
const lateLabel = (order: PurchaseOrder) => `${order.expectOff - order.dueOff}일 지연`

export default function OrderTable({
  rows,
  sort,
  onSort,
  onOpen,
  isFiltered,
  onClearFilters,
  onCreate,
}: Props) {
  // 한 사람만 보고 있으면 담당 영업 열은 모든 줄이 같은 값이라 자리만 차지합니다.
  const { showOwner } = useOwnerScope()
  const columns = useMemo(
    () => ORDER_COLUMNS.filter((col) => col.id !== 'owner' || showOwner),
    [showOwner],
  )

  // 표와 카드는 마크업 자체가 다릅니다. CSS 로는 한쪽을 숨기는 것밖에 못 해
  // 폰에서도 아홉 열짜리 DOM 을 그대로 들고 있게 됩니다.
  const isDesktop = useMediaQuery(`(min-width: ${BP_DESKTOP}px)`)

  if (rows.length === 0) {
    return (
      <div className={styles.card}>
        <div className={styles.empty}>
          {isFiltered ? (
            <>
              <SearchIcon width={34} height={34} strokeWidth={1.5} />
              <p>조건에 맞는 발주가 없습니다.</p>
              <Button variant="outline" onClick={onClearFilters}>
                검색·필터 초기화
              </Button>
            </>
          ) : (
            <>
              <OrdersIcon width={34} height={34} strokeWidth={1.5} />
              <p>아직 등록한 발주가 없습니다.</p>
              <Button onClick={onCreate}>발주 추가</Button>
            </>
          )}
        </div>
      </div>
    )
  }

  if (!isDesktop) {
    return (
      <ul className={styles.cardList}>
        {rows.map((order) => (
          <li key={order.no} className={styles.miniCard} onClick={() => onOpen(order.no)}>
            <div className={styles.miniHead}>
              <button type="button" className={styles.openButton} onClick={() => onOpen(order.no)}>
                {order.hospital}
              </button>
              <span className={[styles.status, styles[TONE_OF[order.status]]].join(' ')}>
                {order.status}
              </span>
            </div>
            <p className={styles.miniItems}>{orderItemLabel(order)}</p>
            <div className={styles.miniMeta}>
              <span className={`${styles.miniAmount} tnum`}>{won(orderTotal(order))}</span>
              <span className="tnum">납기 {fmtDotShort(parseISO(order.due))}</span>
              {isLate(order) ? (
                <span className={styles.late}>{lateLabel(order)}</span>
              ) : (
                <span>{order.supplier}</span>
              )}
            </div>
          </li>
        ))}
      </ul>
    )
  }

  return (
    <div className={styles.card}>
      <div className={styles.scroller}>
        <table
          className={styles.table}
          style={{ width: columns.reduce((sum, col) => sum + col.width, 0) }}
        >
          <caption className="sr-only">발주 목록. 헤더를 눌러 정렬할 수 있습니다.</caption>

          <colgroup>
            {columns.map((col) => (
              <col key={col.id} style={{ width: col.width }} />
            ))}
          </colgroup>

          <thead>
            <tr>
              {columns.map((col) => {
                const active = sort?.id === col.id
                return (
                  <th
                    key={col.id}
                    scope="col"
                    className={col.align === 'right' ? styles.right : undefined}
                    aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  >
                    {col.sortable ? (
                      <button
                        type="button"
                        className={[styles.sortButton, active ? styles.isSorted : '']
                          .filter(Boolean)
                          .join(' ')}
                        onClick={() => onSort(col.id)}
                      >
                        {col.header}
                        {active ? (
                          <ArrowUpIcon
                            width={13}
                            height={13}
                            className={sort.dir === 'desc' ? styles.flip : undefined}
                          />
                        ) : (
                          <SortIcon width={13} height={13} className={styles.sortHint} />
                        )}
                      </button>
                    ) : (
                      <span className={styles.headLabel}>{col.header}</span>
                    )}
                  </th>
                )
              })}
            </tr>
          </thead>

          <tbody>
            {rows.map((order) => {
              const late = isLate(order)
              return (
                <tr key={order.no} className={styles.clickable} onClick={() => onOpen(order.no)}>
                  {columns.map((col) => (
                    <td
                      key={col.id}
                      className={[
                        col.align === 'right' ? styles.right : '',
                        col.numeric ? 'tnum' : '',
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      title={col.text(order)}
                    >
                      {/* 줄 전체를 누르지만 tr 은 키보드로 못 잡습니다. 고객사 칸이
                          그 손잡이이고, 하는 일은 줄을 누른 것과 같습니다. */}
                      {col.id === 'hospital' ? (
                        <button
                          type="button"
                          className={styles.openButton}
                          onClick={(event) => {
                            event.stopPropagation()
                            onOpen(order.no)
                          }}
                        >
                          {order.hospital}
                        </button>
                      ) : col.id === 'status' ? (
                        <span className={[styles.status, styles[TONE_OF[order.status]]].join(' ')}>
                          {order.status}
                        </span>
                      ) : col.id === 'expect' && late ? (
                        <span className={styles.expectLate}>
                          {col.text(order)}
                          <i className={styles.late}>{lateLabel(order)}</i>
                        </span>
                      ) : (
                        col.text(order)
                      )}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
