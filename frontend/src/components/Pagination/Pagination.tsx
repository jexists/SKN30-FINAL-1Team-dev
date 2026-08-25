import { useState } from 'react'

import FilterSelect from '@/components/FilterSelect'
import { ChevronLeftIcon, ChevronRightIcon } from '@/components/icons'

import styles from './Pagination.module.scss'

const PAGE_SIZES = [30, 50, 100]

interface PaginationProps {
  page: number
  pageCount: number
  pageSize: number
  total: number
  /** 세는 단위. 화면마다 다릅니다(고객은 명, 계약은 건). */
  unit?: string
  onPage: (page: number) => void
  onPageSize: (size: number) => void
}

export default function Pagination({
  page,
  pageCount,
  pageSize,
  total,
  unit = '명',
  onPage,
  onPageSize,
}: PaginationProps) {
  const [sizeOpen, setSizeOpen] = useState(false)
  const from = (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)
  const sizeOptions = PAGE_SIZES.map((size) => ({
    value: String(size),
    label: `${size}${unit}`,
  }))

  return (
    <nav className={styles.root} aria-label="페이지 이동">
      <p className={styles.range}>
        <span className="tnum">
          {from}–{to}
        </span>{' '}
        / <span className="tnum">{total}</span>
        {unit}
      </p>

      <div className={styles.controls}>
        <div className={styles.size}>
          페이지당
          <FilterSelect
            label="페이지당 표시 수"
            value={String(pageSize)}
            options={sizeOptions}
            open={sizeOpen}
            compact
            onOpenChange={setSizeOpen}
            onChange={(next) => onPageSize(Number(next))}
          />
        </div>

        <div className={styles.pager}>
          <button
            type="button"
            className={styles.step}
            disabled={page <= 1}
            onClick={() => onPage(page - 1)}
            aria-label="이전 페이지"
          >
            <ChevronLeftIcon width={15} height={15} />
          </button>
          <span className={styles.at}>
            <span className="tnum">{page}</span> / <span className="tnum">{pageCount}</span>
          </span>
          <button
            type="button"
            className={styles.step}
            disabled={page >= pageCount}
            onClick={() => onPage(page + 1)}
            aria-label="다음 페이지"
          >
            <ChevronRightIcon width={15} height={15} />
          </button>
        </div>
      </div>
    </nav>
  )
}
