import { PAGE_SIZE } from '@/constants/pagination'
import { ChevronLeftIcon, ChevronRightIcon } from '@/components/icons'

import styles from './Pagination.module.scss'

interface PaginationProps {
  page: number
  pageCount: number
  total: number
  /** 세는 단위. 화면마다 다릅니다(고객은 명, 계약은 건). */
  unit?: string
  onPage: (page: number) => void
}

export default function Pagination({
  page,
  pageCount,
  total,
  unit = '명',
  onPage,
}: PaginationProps) {
  const from = (page - 1) * PAGE_SIZE + 1
  const to = Math.min(page * PAGE_SIZE, total)

  return (
    <nav className={styles.root} aria-label="페이지 이동">
      <p className={styles.range}>
        <span className="tnum">
          {from}–{to}
        </span>{' '}
        / <span className="tnum">{total}</span>
        {unit}
      </p>

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
    </nav>
  )
}
