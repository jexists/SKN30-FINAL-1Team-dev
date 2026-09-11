import styles from './RecognitionLoading.module.scss'

interface Props {
  description: string
  /** 인식이 아닌 일(업로드 등)에 쓸 때 바꿉니다. */
  title?: string
}

/** 명함·사업자등록증·엑셀 등록에서 공통으로 보여 주는 인식 중 화면입니다. */
export default function RecognitionLoading({ description, title = '인식중입니다' }: Props) {
  return (
    <div className={styles.loading} role="status" aria-live="polite" aria-busy="true">
      <span className={styles.spinner} aria-hidden="true" />
      <strong>{title}</strong>
      <p>{description}</p>
    </div>
  )
}
