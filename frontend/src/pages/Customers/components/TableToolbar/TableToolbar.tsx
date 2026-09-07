import { useState } from 'react'

import Button from '@/components/Button'
import { ColumnsIcon, DownloadIcon } from '@/components/icons'
import Popover from '@/components/Popover'
import SearchInput from '@/components/SearchInput'
import { BP_PHONE } from '@/constants/breakpoints'
import useMediaQuery from '@/hooks/useMediaQuery'

import type { ColumnPrefs } from '../../useColumnPrefs'
import AddCustomerMenu, { type AddCustomerWay } from '../AddCustomerMenu'
import ColumnSettings from '../ColumnSettings'

import styles from './TableToolbar.module.scss'

interface TableToolbarProps {
  query: string
  onSearch: (value: string) => void
  prefs: ColumnPrefs
  onToggleColumn: (id: string) => void
  onMoveColumn: (id: string, delta: -1 | 1) => void
  onResetColumns: () => void
  /** 이 화면에서 아예 쓰지 않는 컬럼. 설정 목록에도 나오지 않습니다. */
  hiddenColumns?: string[]
  /** 고객을 넣는 길을 골랐습니다. 어느 화면을 띄울지는 부른 쪽이 정합니다. */
  onAdd: (way: AddCustomerWay) => void
  onExport: () => void
  /** 내보낼 줄을 모으는 동안. 버튼이 두 번 눌리지 않게 막습니다. */
  exporting?: boolean
  /** 내보낼 고객이 한 명도 없으면 누를 수 없습니다. */
  canExport?: boolean
}

export default function TableToolbar({
  query,
  onSearch,
  prefs,
  onToggleColumn,
  onMoveColumn,
  onResetColumns,
  hiddenColumns,
  onAdd,
  onExport,
  exporting = false,
  canExport = true,
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
        onSearch={onSearch}
      />

      {/* 표를 다루는 도구. 여기 있는 것들은 목록을 바꾸지 않습니다. */}
      <div className={styles.tools}>
        <Popover
          open={open === 'columns'}
          onClose={() => setOpen(null)}
          label="컬럼 설정"
          align={isPhone ? 'start' : 'end'}
          trigger={
            <Button
              variant="outline"
              className={styles.foldLabel}
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
            hidden={hiddenColumns}
          />
        </Popover>

        <Button
          variant="outline"
          className={styles.foldLabel}
          aria-label="고객 목록 엑셀로 내보내기"
          disabled={exporting || !canExport}
          onClick={onExport}
        >
          <DownloadIcon width={15} height={15} />
          <span>{exporting ? '모으는 중…' : '내보내기'}</span>
        </Button>
      </div>

      {/*
        고객을 넣는 네 갈래. 결과가 같은 일이라 버튼 하나로 모으고, 무엇으로 넣을지는
        메뉴에서 고릅니다. 넷을 따로 띄우면 무엇이 주된 길인지 사라집니다.
      */}
      <div className={styles.add}>
        <AddCustomerMenu onSelect={onAdd} />
      </div>
    </div>
  )
}
