// 표 한 줄의 관리 버튼. 수정·숨김 전환·삭제를 묶습니다.
import Button from '@/components/Button'
import type { NoticeManageListResponse } from '@/types'

import styles from '../Notices.module.scss'

interface Props {
  row: NoticeManageListResponse
  busy: boolean
  onEdit: () => void
  onToggleHidden: () => void
  onDelete: () => void
}

export default function NoticeRowActions({ row, busy, onEdit, onToggleHidden, onDelete }: Props) {
  return (
    <div className={styles.rowActions}>
      <Button type="button" variant="outline" size="sm" disabled={busy} onClick={onEdit}>
        수정
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={busy}
        aria-pressed={row.is_hidden}
        onClick={onToggleHidden}
      >
        {row.is_hidden ? '보이기' : '숨기기'}
      </Button>
      <button type="button" className={styles.remove} disabled={busy} onClick={onDelete}>
        삭제
      </button>
    </div>
  )
}
