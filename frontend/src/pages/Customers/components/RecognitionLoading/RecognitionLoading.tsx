import ProgressBar from '@/components/ProgressBar'

import styles from './RecognitionLoading.module.scss'

interface Props {
  description: string
  progress?: number
}

/** 명함·사업자등록증·엑셀 등록에서 공통으로 보여 주는 인식 중 화면입니다. */
export default function RecognitionLoading({ description, progress }: Props) {
  return (
    <div className={styles.loading} role="status" aria-live="polite" aria-busy="true">
      <span className={styles.spinner} aria-hidden="true" />
      <strong>인식중입니다</strong>
      <p>{description}</p>
      <ProgressBar
        value={progress}
        label={`인식중입니다. ${description}`}
        className={styles.progress}
      />
    </div>
  )
}
