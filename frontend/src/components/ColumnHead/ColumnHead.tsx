// 보고서 작성 화면의 열 머리. 왼쪽은 그 열이 무엇인지, 오른쪽 끝은 그 열에서 하는 일입니다.
//
// 미팅과 일일·주간·월간의 네 열이 이것을 씁니다. 넷이 다르면 나란히 놓았을 때 줄이 어긋납니다.
import type { ReactNode } from 'react'

import styles from './ColumnHead.module.scss'

type Props = {
  /** 접힌 열처럼 제목이 물러난 줄에서는 비웁니다. */
  title?: ReactNode
  /** 제목이 물러나면 경계선과 들여쓰기도 함께 뺍니다. */
  bare?: boolean
  /** 줄 오른쪽 끝에 서는 조작부(접기 손잡이, PDF 내려받기). */
  children?: ReactNode
}

export default function ColumnHead({ title, bare, children }: Props) {
  return (
    <div className={bare ? `${styles.head} ${styles.bare}` : styles.head}>
      {title && <h2>{title}</h2>}
      {children}
    </div>
  )
}
