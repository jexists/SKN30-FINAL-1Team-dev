// demo/layout_v3.html 의 #listDrawer 입니다.
// 대시보드의 모든 카운터 뒤에 이 드로어 하나가 섭니다. KPI 타일이면 필터 없이,
// 발주 타일이면 위에 필터 칩을 달고 같은 표면을 씁니다.
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import { ChevronRightIcon } from '@/components/icons'
import OwnerName from '@/components/OwnerName'
import { SkeletonBlocks } from '@/components/Skeleton'
import { useShowOwner } from '@/shared/scope'

import type { DrawerList, DrawerListRow } from '../../drawerLists'
import type { OrderFilterKey } from '../../orderFilters'

import styles from './ListDrawer.module.scss'

interface Props {
  list: DrawerList
  /** KPI 목록은 눌러야 받아 옵니다. 발주 목록은 이미 손에 있어 이 셋을 주지 않습니다. */
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  /** 아직 안 받은 건수. 0 이면 버튼이 서지 않습니다. 발주 목록은 이미 다 손에 있어 주지 않습니다. */
  remaining?: number
  loadingMore?: boolean
  onLoadMore?: () => void
  /** 있으면 머리말 아래에 필터 칩이 붙습니다. 발주 목록에서만 씁니다. */
  filters?: { key: OrderFilterKey; label: string; n: number }[]
  activeFilter?: OrderFilterKey
  onFilter?: (key: OrderFilterKey) => void
  onOpenOrder?: (no: string) => void
  /** 있으면 링크 줄이 화면을 옮기지 않고 이것을 부릅니다. 상세는 `side` 로 옆에 펼칩니다. */
  onOpenRow?: (key: string) => void
  activeKey?: string | null
  side?: ReactNode
  onSideDismiss?: () => void
  onClose: () => void
}

function Row({
  row,
  showOwner,
  linked,
}: {
  row: DrawerListRow
  showOwner: boolean
  linked?: boolean
}) {
  return (
    <>
      <div className={styles.main}>
        <h3>
          {row.title}
          {row.titleNote && <span>{row.titleNote}</span>}
          {row.titleTag && (
            <i className={`${styles.pill} ${row.titleTag.tone ? styles[row.titleTag.tone] : ''}`}>
              {row.titleTag.text}
            </i>
          )}
        </h3>
        {row.note && <p>{row.note}</p>}
        {(row.tags.length > 0 || (showOwner && row.owner)) && (
          <div className={styles.tags}>
            {showOwner && <OwnerName name={row.owner} memberId={row.ownerMemberId} />}
            {row.tags.map((t) => (
              <i key={t.text} className={`${styles.pill} ${t.tone ? styles[t.tone] : ''}`}>
                {t.text}
              </i>
            ))}
          </div>
        )}
      </div>

      <div className={styles.side}>
        {row.side.strong && (
          <strong
            className={[row.side.numeric && 'tnum', row.side.late && styles.late]
              .filter(Boolean)
              .join(' ')}
          >
            {row.side.strong}
          </strong>
        )}
        {row.side.lines?.map((line) => (
          <span key={line.text} className={line.numeric ? 'tnum' : undefined}>
            {line.text}
          </span>
        ))}
        {/* 제 화면으로 넘어가는 줄이라는 표시. 펼치는 줄과 같은 자리에 방향만 달리 섭니다. */}
        {linked && <ChevronRightIcon className={styles.caret} width={15} height={15} />}
      </div>
    </>
  )
}

export default function ListDrawer({
  list,
  loading,
  error,
  onRetry,
  remaining = 0,
  loadingMore,
  onLoadMore,
  filters,
  activeFilter,
  onFilter,
  onOpenOrder,
  onOpenRow,
  activeKey,
  side,
  onSideDismiss,
  onClose,
}: Props) {
  const showOwner = useShowOwner()

  return (
    <Drawer
      wide
      title={list.title}
      sub={list.sub}
      onClose={onClose}
      side={side}
      keepMain
      onSideDismiss={onSideDismiss}
      resetKey={activeFilter}
      filters={
        filters &&
        filters.map((f) => (
          <button
            key={f.key}
            type="button"
            className={styles.filter}
            aria-pressed={f.key === activeFilter}
            onClick={() => onFilter?.(f.key)}
          >
            {f.label} <span className="tnum">{f.n}</span>
          </button>
        ))
      }
    >
      {error ? (
        <p className={styles.empty} role="alert">
          {error}{' '}
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry}>
              다시 시도
            </Button>
          )}
        </p>
      ) : loading ? (
        <SkeletonBlocks label="목록을 불러오는 중입니다." count={4} height={66} />
      ) : list.rows.length === 0 ? (
        <p className={styles.empty}>{list.empty ?? '표시할 항목이 없습니다.'}</p>
      ) : (
        <>
          {list.rows.map((row) => {
            // 발주 줄은 발주 드로어를, 나머지 줄은 제 화면을 엽니다.
            const no = row.orderNo

            if (row.href && onOpenRow) {
              return (
                <div key={row.key} className={styles.item}>
                  <button
                    type="button"
                    className={`${styles.row} ${styles.clickable}`}
                    aria-current={activeKey === row.key}
                    onClick={() => onOpenRow(row.key)}
                  >
                    <Row row={row} showOwner={showOwner} linked />
                  </button>
                </div>
              )
            }

            if (row.href) {
              return (
                <div key={row.key} className={styles.item}>
                  <Link to={row.href} className={`${styles.row} ${styles.clickable}`}>
                    <Row row={row} showOwner={showOwner} linked />
                  </Link>
                </div>
              )
            }

            if (no && onOpenOrder) {
              return (
                <div key={row.key} className={styles.item}>
                  <button
                    type="button"
                    className={`${styles.row} ${styles.clickable}`}
                    onClick={() => onOpenOrder(no)}
                  >
                    <Row row={row} showOwner={showOwner} />
                  </button>
                </div>
              )
            }

            return (
              <div key={row.key} className={styles.item}>
                <div className={styles.row}>
                  <Row row={row} showOwner={showOwner} />
                </div>
              </div>
            )
          })}

          {remaining > 0 && (
            <button
              type="button"
              className={styles.more}
              disabled={loadingMore}
              onClick={onLoadMore}
            >
              {loadingMore ? '불러오는 중입니다…' : `${remaining}건 더 보기`}
            </button>
          )}
        </>
      )}
    </Drawer>
  )
}
