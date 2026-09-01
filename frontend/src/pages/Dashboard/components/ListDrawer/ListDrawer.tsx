// demo/layout_v3.html 의 #listDrawer 입니다.
// 대시보드의 모든 카운터 뒤에 이 드로어 하나가 섭니다. KPI 타일이면 필터 없이,
// 발주 타일이면 위에 필터 칩을 달고 같은 표면을 씁니다.
import { useState } from 'react'

import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import { ChevronDownIcon } from '@/components/icons'
import OwnerName from '@/components/OwnerName'
import { InlineLoader } from '@/components/Skeleton'
import { useShowOwner } from '@/shared/scope'

import type { DrawerList, DrawerListDetail, DrawerListRow } from '../../drawerLists'
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
  onClose: () => void
}

function Row({
  row,
  showOwner,
  expandable,
  expanded,
}: {
  row: DrawerListRow
  showOwner: boolean
  expandable?: boolean
  expanded?: boolean
}) {
  return (
    <>
      <div className={styles.main}>
        <h3>
          {row.title}
          {row.titleNote && <span>{row.titleNote}</span>}
        </h3>
        <p>{row.note}</p>
        {(row.tags.length > 0 || (showOwner && row.owner)) && (
          <div className={styles.tags}>
            {showOwner && <OwnerName name={row.owner} />}
            {row.tags.map((t) => (
              <i key={t.text} className={`${styles.pill} ${t.tone ? styles[t.tone] : ''}`}>
                {t.text}
              </i>
            ))}
          </div>
        )}
      </div>

      <div className={styles.side}>
        <strong
          className={[row.side.numeric && 'tnum', row.side.late && styles.late]
            .filter(Boolean)
            .join(' ')}
        >
          {row.side.strong}
        </strong>
        {row.side.lines?.map((line) => (
          <span key={line.text} className={line.numeric ? 'tnum' : undefined}>
            {line.text}
          </span>
        ))}
        {/* 펼칠 수 있는 줄이라는 표시. 눌러야 알 수 있으면 아무도 누르지 않습니다. */}
        {expandable && (
          <ChevronDownIcon
            className={`${styles.caret} ${expanded ? styles.up : ''}`}
            width={15}
            height={15}
          />
        )}
      </div>
    </>
  )
}

function Detail({ detail }: { detail: DrawerListDetail }) {
  return (
    <div className={styles.detail}>
      <dl>
        {detail.fields.map((field) => (
          <div key={field.label}>
            <dt>{field.label}</dt>
            <dd>{field.value}</dd>
          </div>
        ))}
      </dl>

      {detail.notes && (
        <section className={styles.notes}>
          <h4>{detail.notesTitle ?? '이력'}</h4>
          {detail.notes.length === 0 ? (
            <p className={styles.noNotes}>{detail.notesEmpty ?? '등록된 이력이 없습니다.'}</p>
          ) : (
            <ol>
              {detail.notes.map((note) => (
                <li key={note.key}>
                  <div>
                    <strong>{note.by}</strong>
                    <span>{note.at}</span>
                  </div>
                  <p>{note.body}</p>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </div>
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
  onClose,
}: Props) {
  const showOwner = useShowOwner()
  // 한 번에 한 줄만 펼칩니다. 여러 줄이 열리면 목록이 길어져 다시 찾기 어렵습니다.
  const [openKey, setOpenKey] = useState<string | null>(null)

  return (
    <Drawer
      wide
      title={list.title}
      sub={list.sub}
      onClose={onClose}
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
        <InlineLoader label="목록을 불러오는 중입니다." />
      ) : list.rows.length === 0 ? (
        <p className={styles.empty}>{list.empty ?? '표시할 항목이 없습니다.'}</p>
      ) : (
        <>
          {list.rows.map((row) => {
            // 발주 줄은 제 화면으로 넘어갑니다. 상세를 들고 있는 줄은 그 자리에서 펼칩니다.
            const no = row.orderNo
            const detail = row.detail
            const expanded = openKey === row.key
            const panelId = `list-row-${row.key}`

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

            if (detail) {
              return (
                <div key={row.key} className={styles.item}>
                  <button
                    type="button"
                    className={`${styles.row} ${styles.clickable}`}
                    aria-expanded={expanded}
                    aria-controls={panelId}
                    onClick={() => setOpenKey(expanded ? null : row.key)}
                  >
                    <Row row={row} showOwner={showOwner} expandable expanded={expanded} />
                  </button>
                  {expanded && (
                    <div id={panelId}>
                      <Detail detail={detail} />
                    </div>
                  )}
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
