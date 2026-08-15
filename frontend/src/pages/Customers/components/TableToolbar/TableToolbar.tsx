import { useState } from 'react'

import Button from '@/components/Button'
import { ColumnsIcon, DownloadIcon, PlusIcon, SearchIcon, UploadIcon } from '@/components/icons'
import Popover from '@/components/Popover'

import type { ColumnPrefs } from '../../useColumnPrefs'
import ColumnSettings from '../ColumnSettings'

import styles from './TableToolbar.module.scss'

interface TableToolbarProps {
  query: string
  onQueryChange: (value: string) => void
  prefs: ColumnPrefs
  onToggleColumn: (id: string) => void
  onMoveColumn: (id: string, delta: -1 | 1) => void
  onResetColumns: () => void
  onExport: () => void
  onImport: () => void
  onCreate: () => void
}

export default function TableToolbar({
  query,
  onQueryChange,
  prefs,
  onToggleColumn,
  onMoveColumn,
  onResetColumns,
  onExport,
  onImport,
  onCreate,
}: TableToolbarProps) {
  const [open, setOpen] = useState<'columns' | null>(null)

  return (
    <div className={styles.root}>
      <div className={styles.search}>
        <SearchIcon width={16} height={16} />
        <input
          type="search"
          value={query}
          placeholder="이름, 회사, 직함, 메모 검색"
          onChange={(event) => onQueryChange(event.target.value)}
          aria-label="고객 검색"
        />
      </div>

      <div className={styles.tools}>
        <Popover
          open={open === 'columns'}
          onClose={() => setOpen(null)}
          label="컬럼 설정"
          align="end"
          trigger={
            <button
              type="button"
              className={styles.tool}
              aria-expanded={open === 'columns'}
              onClick={() => setOpen(open === 'columns' ? null : 'columns')}
            >
              <ColumnsIcon width={15} height={15} />
              컬럼 설정
            </button>
          }
        >
          <ColumnSettings
            prefs={prefs}
            onToggle={onToggleColumn}
            onMove={onMoveColumn}
            onReset={onResetColumns}
          />
        </Popover>

        <button type="button" className={styles.tool} onClick={onImport}>
          <UploadIcon width={15} height={15} />
          가져오기
        </button>

        <button type="button" className={styles.tool} onClick={onExport}>
          <DownloadIcon width={15} height={15} />
          내보내기
        </button>
      </div>

      <Button className={styles.create} onClick={onCreate}>
        <PlusIcon width={16} height={16} />
        고객 등록
      </Button>
    </div>
  )
}
