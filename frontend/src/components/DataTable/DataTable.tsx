// 목록 표입니다. 줄 하나가 기록 한 건이고, 누르면 오른쪽 드로어가 섭니다.
// 영업·견적·계약·발주 네 목록이 이 하나를 씁니다.
//
// 열 폭 조절·선택 체크박스는 두지 않습니다. 여기서 하는 일은 훑어보고 여는 것뿐이라
// 고객 목록만큼의 도구가 필요하지 않습니다.
//
// 폰에서는 표 대신 카드를 그립니다. 마크업 자체가 달라 CSS 로는 한쪽을 숨기는 것밖에
// 못 하고, 그러면 폰에서도 아홉 열짜리 DOM 을 그대로 들고 있게 됩니다.
import type { ReactNode } from 'react'

import { ArrowUpIcon, SortIcon } from '@/components/icons'
import { BP_DESKTOP } from '@/constants/breakpoints'
import useMediaQuery from '@/hooks/useMediaQuery'

import type { DataColumn, SortState } from './columns'

import styles from './DataTable.module.scss'

/** 폰에서 그리는 카드 한 장의 내용 */
export interface MiniCard {
  /** 굵게 나오는 첫 줄. 누르면 열립니다. */
  title: string
  /** 첫 줄 오른쪽 배지 */
  badge?: ReactNode
  /** 둘째 줄 */
  sub: string
  /** 셋째 줄. 첫 칸은 금액처럼 굵게 나옵니다. */
  meta: ReactNode[]
}

interface Props<T> {
  rows: T[]
  columns: DataColumn<T>[]
  rowKey: (row: T) => string
  /** 누르면 열리는 손잡이가 될 열. 보통 고객사 칸입니다. */
  handleColumn: string
  sort: SortState
  onSort: (id: string) => void
  onOpen: (row: T) => void
  /** 스크린리더용 표 설명 */
  caption: string
  /** 배지처럼 글자만으로는 안 되는 칸. undefined 를 돌려주면 col.text 를 씁니다. */
  renderCell?: (columnId: string, row: T) => ReactNode | undefined
  mini: (row: T) => MiniCard
  /** 줄이 하나도 없을 때 그릴 것 */
  empty: ReactNode
}

export default function DataTable<T>({
  rows,
  columns,
  rowKey,
  handleColumn,
  sort,
  onSort,
  onOpen,
  caption,
  renderCell,
  mini,
  empty,
}: Props<T>) {
  const isDesktop = useMediaQuery(`(min-width: ${BP_DESKTOP}px)`)

  if (rows.length === 0) {
    return (
      <div className={styles.card}>
        <div className={styles.empty}>{empty}</div>
      </div>
    )
  }

  if (!isDesktop) {
    return (
      <ul className={styles.cardList}>
        {rows.map((row) => {
          const card = mini(row)
          return (
            <li key={rowKey(row)} className={styles.miniCard} onClick={() => onOpen(row)}>
              <div className={styles.miniHead}>
                <button type="button" className={styles.openButton} onClick={() => onOpen(row)}>
                  {card.title}
                </button>
                {card.badge}
              </div>
              <p className={styles.miniSub}>{card.sub}</p>
              <div className={styles.miniMeta}>
                {card.meta.map((part, at) => (
                  // 칸의 내용이 곧 자리라 순번 말고 쓸 열쇠가 없습니다.
                  // eslint-disable-next-line react/no-array-index-key
                  <span key={at} className={at === 0 ? styles.miniLead : undefined}>
                    {part}
                  </span>
                ))}
              </div>
            </li>
          )
        })}
      </ul>
    )
  }

  return (
    <div className={styles.card}>
      <div className={styles.scroller}>
        {/*
          폭은 열 합계를 최소 폭으로만 받습니다. 남으면 표가 카드를 가득 채우고,
          모자랄 때만 가로로 넘칩니다. 예전에는 width 로 줘서 합계가 본문보다 넓으면
          마지막 열이 잘려 보였습니다.
        */}
        <table
          className={styles.table}
          style={{ minWidth: columns.reduce((sum, col) => sum + col.width, 0) }}
        >
          <caption className="sr-only">{caption}</caption>

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
            {rows.map((row) => (
              <tr key={rowKey(row)} className={styles.clickable} onClick={() => onOpen(row)}>
                {columns.map((col) => {
                  const custom = renderCell?.(col.id, row)
                  return (
                    <td
                      key={col.id}
                      className={[
                        col.align === 'right' ? styles.right : '',
                        col.numeric ? 'tnum' : '',
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      title={col.text(row)}
                    >
                      {/* 줄 전체를 누르지만 tr 은 키보드로 못 잡습니다. 고객사 칸이
                          그 손잡이이고, 하는 일은 줄을 누른 것과 같습니다. */}
                      {col.id === handleColumn ? (
                        <button
                          type="button"
                          className={styles.openButton}
                          onClick={(event) => {
                            event.stopPropagation()
                            onOpen(row)
                          }}
                        >
                          {col.text(row)}
                        </button>
                      ) : (
                        (custom ?? col.text(row))
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
