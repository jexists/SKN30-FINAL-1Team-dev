import { CloseIcon } from '@/components/icons'

import styles from './SelectionBar.module.scss'

interface SelectionBarProps {
  count: number
  onClear: () => void
}

export default function SelectionBar({ count, onClear }: SelectionBarProps) {
  return (
    <div className={styles.root} role="status">
      <p className={styles.count}>
        <span className="tnum">{count}</span>명 선택
      </p>

      <div className={styles.actions}>
        <button type="button" className={styles.close} onClick={onClear} aria-label="선택 해제">
          <CloseIcon width={15} height={15} />
        </button>
      </div>
    </div>
  )
}
