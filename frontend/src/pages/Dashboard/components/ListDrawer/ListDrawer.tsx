// demo/layout_v3.html 의 #listDrawer 입니다.
// 대시보드의 모든 카운터 뒤에 이 드로어 하나가 섭니다. KPI 타일이면 필터 없이,
// 발주 타일이면 위에 필터 칩을 달고 같은 표면을 씁니다.
import Drawer from '@/components/Drawer'

import type { DrawerList, DrawerListRow } from '../../drawerLists'
import type { OrderFilterKey } from '../../orderFilters'

import styles from './ListDrawer.module.scss'

interface Props {
  list: DrawerList
  /** 있으면 머리말 아래에 필터 칩이 붙습니다. 발주 목록에서만 씁니다. */
  filters?: { key: OrderFilterKey; label: string; n: number }[]
  activeFilter?: OrderFilterKey
  onFilter?: (key: OrderFilterKey) => void
  onOpenOrder?: (no: string) => void
  onClose: () => void
}

function Row({ row }: { row: DrawerListRow }) {
  return (
    <>
      <div className={styles.main}>
        <h3>
          {row.title}
          {row.titleNote && <span>{row.titleNote}</span>}
        </h3>
        <p>{row.note}</p>
        {row.tags.length > 0 && (
          <div className={styles.tags}>
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
      </div>
    </>
  )
}

export default function ListDrawer({
  list,
  filters,
  activeFilter,
  onFilter,
  onOpenOrder,
  onClose,
}: Props) {
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
      {list.rows.length === 0 ? (
        <p className={styles.empty}>{list.empty ?? '표시할 항목이 없습니다.'}</p>
      ) : (
        list.rows.map((row) => {
          // 발주 줄만 더 들어갈 데가 있어 버튼입니다. 나머지는 여기가 끝입니다.
          const no = row.orderNo
          return no && onOpenOrder ? (
            <button
              key={row.key}
              type="button"
              className={`${styles.row} ${styles.clickable}`}
              onClick={() => onOpenOrder(no)}
            >
              <Row row={row} />
            </button>
          ) : (
            <div key={row.key} className={styles.row}>
              <Row row={row} />
            </div>
          )
        })
      )}
    </Drawer>
  )
}
