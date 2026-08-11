import { CloseIcon, DownloadIcon, TrashIcon } from '@/components/icons'

import styles from './SelectionBar.module.scss'

interface SelectionBarProps {
  count: number
  onExport: () => void
  onDelete: () => void
  onClear: () => void
}

export default function SelectionBar({ count, onExport, onDelete, onClear }: SelectionBarProps) {
  return (
    <div className={styles.root} role="status">
      <p className={styles.count}>
        <span className="tnum">{count}</span>명 선택
      </p>

      <div className={styles.actions}>
        <button type="button" className={styles.action} onClick={onExport}>
          <DownloadIcon width={15} height={15} />
          선택 내보내기
        </button>
        <button type="button" className={`${styles.action} ${styles.danger}`} onClick={onDelete}>
          <TrashIcon width={15} height={15} />
          목록에서 제거
        </button>
        <button type="button" className={styles.close} onClick={onClear} aria-label="선택 해제">
          <CloseIcon width={15} height={15} />
        </button>
      </div>
    </div>
  )
}
