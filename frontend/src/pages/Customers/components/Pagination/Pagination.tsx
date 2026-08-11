import { ChevronLeftIcon, ChevronRightIcon } from '@/components/icons'

import styles from './Pagination.module.scss'

const PAGE_SIZES = [25, 50, 100]

interface PaginationProps {
  page: number
  pageCount: number
  pageSize: number
  total: number
  onPage: (page: number) => void
  onPageSize: (size: number) => void
}

export default function Pagination({
  page,
  pageCount,
  pageSize,
  total,
  onPage,
  onPageSize,
}: PaginationProps) {
  const from = (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)

  return (
    <nav className={styles.root} aria-label="페이지 이동">
      <p className={styles.range}>
        <span className="tnum">
          {from}–{to}
        </span>{' '}
        / <span className="tnum">{total}</span>명
      </p>

      <div className={styles.controls}>
        <label className={styles.size}>
          페이지당
          <select value={pageSize} onChange={(event) => onPageSize(Number(event.target.value))}>
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}명
              </option>
            ))}
          </select>
        </label>

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
