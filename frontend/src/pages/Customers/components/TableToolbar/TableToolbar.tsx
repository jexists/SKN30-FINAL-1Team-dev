import { useState } from 'react'

import Button from '@/components/Button'
import { ColumnsIcon, PlusIcon } from '@/components/icons'
import Popover from '@/components/Popover'
import SearchInput from '@/components/SearchInput'
import { BP_PHONE } from '@/constants/breakpoints'
import useMediaQuery from '@/hooks/useMediaQuery'

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
  onCreate: () => void
}

export default function TableToolbar({
  query,
  onQueryChange,
  prefs,
  onToggleColumn,
  onMoveColumn,
  onResetColumns,
  onCreate,
}: TableToolbarProps) {
  const [open, setOpen] = useState<'columns' | null>(null)
  // 폰에서는 이 버튼이 줄 맨 왼쪽이라, 오른쪽 정렬하면 판이 화면 밖으로 나갑니다.
  const isPhone = useMediaQuery(`(max-width: ${BP_PHONE}px)`)

  return (
    <div className={styles.root}>
      <SearchInput
        className={styles.search}
        value={query}
        placeholder="이름, 회사, 부서, 직함, 이메일, 전화 검색"
        label="고객 검색"
        onChange={onQueryChange}
      />

      <div className={styles.tools}>
        <Popover
          open={open === 'columns'}
          onClose={() => setOpen(null)}
          label="컬럼 설정"
          align={isPhone ? 'start' : 'end'}
          trigger={
            <Button
              variant="outline"
              aria-expanded={open === 'columns'}
              aria-label="컬럼 설정"
              onClick={() => setOpen(open === 'columns' ? null : 'columns')}
            >
              <ColumnsIcon width={15} height={15} />
              <span>컬럼 설정</span>
            </Button>
          }
        >
          <ColumnSettings
            prefs={prefs}
            onToggle={onToggleColumn}
            onMove={onMoveColumn}
            onReset={onResetColumns}
          />
        </Popover>
      </div>

      <Button className={styles.create} onClick={onCreate}>
        <PlusIcon width={16} height={16} />
        고객 등록
      </Button>
    </div>
  )
}
