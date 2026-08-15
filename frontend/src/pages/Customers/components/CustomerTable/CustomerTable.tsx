import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'

import Button from '@/components/Button'
import { ArrowUpIcon, CustomersIcon, SearchIcon, SortIcon } from '@/components/icons'
import { BP_DESKTOP } from '@/constants/breakpoints'
import type { Customer } from '@/types'
import useMediaQuery from '@/hooks/useMediaQuery'

import type { ColumnDef } from '../../columns'
import type { SortState } from '../../Customers'

import styles from './CustomerTable.module.scss'

/** 체크박스 열의 폭. 이름 열을 그 옆에 붙여 고정하는 데 씁니다. */
const CHECK_W = 44

interface CustomerTableProps {
  columns: ColumnDef[]
  widths: Record<string, number>
  onResize: (id: string, width: number) => void
  rows: Customer[]
  sort: SortState
  onSort: (id: string) => void
  selected: ReadonlySet<string>
  onToggleRow: (id: string) => void
  onTogglePage: () => void
  /** 줄을 누르면 그 고객의 상세 드로어가 섭니다. */
  onOpen: (id: string) => void
  isFiltered: boolean
  hasAnyData: boolean
  onClearFilters: () => void
  onCreate: () => void
}

export default function CustomerTable({
  columns,
  widths,
  onResize,
  rows,
  sort,
  onSort,
  selected,
  onToggleRow,
  onTogglePage,
  onOpen,
  isFiltered,
  hasAnyData,
  onClearFilters,
  onCreate,
}: CustomerTableProps) {
  // 표와 카드는 마크업 자체가 다릅니다. CSS 로는 한쪽을 숨기는 것밖에 못 해
  // 폰에서도 12열짜리 DOM 을 그대로 들고 있게 됩니다.
  const isDesktop = useMediaQuery(`(min-width: ${BP_DESKTOP}px)`)

  const headCheck = useRef<HTMLInputElement>(null)
  const allChecked = rows.length > 0 && rows.every((r) => selected.has(r.id))
  const someChecked = rows.some((r) => selected.has(r.id))

  useEffect(() => {
    // indeterminate 는 속성이 아니라 DOM 프로퍼티라 JSX 로 못 넘깁니다.
    if (headCheck.current) headCheck.current.indeterminate = someChecked && !allChecked
  }, [someChecked, allChecked])

  // 끄는 동안의 폭은 여기에만 둡니다. 저장은 손을 뗄 때 한 번입니다.
  const [drag, setDrag] = useState<{ id: string; width: number } | null>(null)

  const widthOf = useCallback(
    (col: ColumnDef) => (drag?.id === col.id ? drag.width : (widths[col.id] ?? col.width)),
    [drag, widths],
  )

  // 고정 열은 체크박스 오른쪽에 차례로 붙습니다. 앞선 고정 열의 폭만큼 밀어 줍니다.
  const stickyLeft = new Map<string, number>()
  let offset = CHECK_W
  for (const col of columns) {
    if (!col.fixed) break
    stickyLeft.set(col.id, offset)
    offset += widthOf(col)
  }

  const stickyStyle = (col: ColumnDef) =>
    col.fixed ? ({ '--sticky-left': `${stickyLeft.get(col.id)}px` } as CSSProperties) : undefined

  if (rows.length === 0) {
    return (
      <div className={styles.card}>
        <div className={styles.empty}>
          {isFiltered ? (
            <>
              <SearchIcon width={34} height={34} strokeWidth={1.5} />
              <p>조건에 맞는 고객이 없습니다.</p>
              <Button variant="outline" onClick={onClearFilters}>
                검색 초기화
              </Button>
            </>
          ) : (
            <>
              <CustomersIcon width={34} height={34} strokeWidth={1.5} />
              <p>{hasAnyData ? '표시할 고객이 없습니다.' : '아직 등록한 고객이 없습니다.'}</p>
              <Button onClick={onCreate}>고객 등록</Button>
            </>
          )}
        </div>
      </div>
    )
  }

  if (!isDesktop) {
    return (
      <ul className={styles.cardList}>
        {rows.map((row) => (
          // 카드 어디를 눌러도 상세가 열립니다. 체크박스는 할 일이 따로 있어 막습니다.
          <li
            key={row.id}
            className={`${styles.miniCard} ${styles.clickable} ${
              selected.has(row.id) ? styles.isSelected : ''
            }`}
            onClick={() => onOpen(row.id)}
          >
            <label className={styles.miniCheck} onClick={(event) => event.stopPropagation()}>
              <input
                type="checkbox"
                checked={selected.has(row.id)}
                onChange={() => onToggleRow(row.id)}
              />
              <span className="sr-only">{row.name} 선택</span>
            </label>
            <div className={styles.miniBody}>
              <p className={styles.miniName}>
                <button
                  type="button"
                  className={styles.openButton}
                  onClick={(event) => {
                    event.stopPropagation()
                    onOpen(row.id)
                  }}
                >
                  {row.name}
                </button>
              </p>
              {/* 직함이 비면 가운뎃점만 덩그러니 남습니다. */}
              <p className={styles.miniOrg}>{[row.org, row.title].filter(Boolean).join(' · ')}</p>
              <p className={styles.miniMeta}>{row.owner}</p>
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
          style={{ width: CHECK_W + columns.reduce((sum, col) => sum + widthOf(col), 0) }}
        >
          <caption className="sr-only">고객 목록. 헤더를 눌러 정렬할 수 있습니다.</caption>

          <colgroup>
            <col style={{ width: CHECK_W }} />
            {columns.map((col) => (
              <col key={col.id} style={{ width: widthOf(col) }} />
            ))}
          </colgroup>

          <thead>
            <tr>
              <th scope="col" className={`${styles.checkCell} ${styles.stickyCheck}`}>
                <input
                  ref={headCheck}
                  type="checkbox"
                  checked={allChecked}
                  onChange={onTogglePage}
                  aria-label="이 페이지 전체 선택"
                />
              </th>

              {columns.map((col) => {
                const active = sort?.id === col.id
                return (
                  <th
                    key={col.id}
                    scope="col"
                    className={col.fixed ? styles.stickyName : undefined}
                    style={stickyStyle(col)}
                    aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  >
                    {col.sortable ? (
                      <button
                        type="button"
                        className={`${styles.sortButton} ${active ? styles.isSorted : ''}`}
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

                    <ResizeHandle
                      column={col}
                      width={widthOf(col)}
                      onPreview={setDrag}
                      onCommit={onResize}
                    />
                  </th>
                )
              })}
            </tr>
          </thead>

          <tbody>
            {rows.map((row) => {
              const isSelected = selected.has(row.id)
              return (
                <tr
                  key={row.id}
                  className={`${styles.clickable} ${isSelected ? styles.isSelected : ''}`}
                  onClick={() => onOpen(row.id)}
                >
                  <td
                    className={`${styles.checkCell} ${styles.stickyCheck}`}
                    onClick={(event) => event.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => onToggleRow(row.id)}
                      aria-label={`${row.name} 선택`}
                    />
                  </td>

                  {columns.map((col) => {
                    const cell = col.render ? col.render(row) : col.value(row)
                    return (
                      <td
                        key={col.id}
                        className={col.fixed ? styles.stickyName : undefined}
                        style={stickyStyle(col)}
                        title={col.value(row)}
                      >
                        {/* 줄 전체를 누르지만 tr 은 키보드로 못 잡습니다. 고정된 이름
                            열이 그 손잡이이고, 하는 일은 줄을 누른 것과 같습니다. */}
                        {col.id === 'name' ? (
                          <button
                            type="button"
                            className={styles.openButton}
                            onClick={(event) => {
                              event.stopPropagation()
                              onOpen(row.id)
                            }}
                          >
                            {cell}
                          </button>
                        ) : (
                          cell
                        )}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

interface ResizeHandleProps {
  column: ColumnDef
  width: number
  onPreview: (drag: { id: string; width: number } | null) => void
  onCommit: (id: string, width: number) => void
}

/**
 * 헤더 경계를 끌어 폭을 바꿉니다.
 * 끄는 동안은 미리보기 상태로만 그리고 손을 뗄 때 한 번만 저장합니다.
 * 프레임마다 저장하면 localStorage 쓰기가 초당 수십 번 일어납니다.
 */
function ResizeHandle({ column, width, onPreview, onCommit }: ResizeHandleProps) {
  const drag = useRef<{ x: number; w: number; latest: number } | null>(null)

  const finish = () => {
    if (!drag.current) return
    onCommit(column.id, drag.current.latest)
    drag.current = null
    onPreview(null)
  }

  return (
    <span
      className={styles.resizer}
      role="separator"
      aria-orientation="vertical"
      aria-label={`${column.header} 열 너비 조절`}
      onPointerDown={(event) => {
        event.preventDefault()
        event.currentTarget.setPointerCapture(event.pointerId)
        drag.current = { x: event.clientX, w: width, latest: width }
      }}
      onPointerMove={(event) => {
        if (!drag.current) return
        const next = Math.max(column.minWidth, drag.current.w + event.clientX - drag.current.x)
        drag.current.latest = next
        onPreview({ id: column.id, width: next })
      }}
      onPointerUp={finish}
      onPointerCancel={finish}
    />
  )
}
