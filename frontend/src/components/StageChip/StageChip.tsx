// 단계 배지. 표·카드·드로어가 같은 단계를 같은 색으로 보여 줍니다.
//
// 색을 여기 한 곳에만 두는 이유: 예전에는 표마다 톤 블록을 복붙해 두어서
// 단계를 하나 늘릴 때마다 고칠 곳이 셋이었습니다.
import type { ReactNode } from 'react'

import type { ColumnTone } from '@/types'

import styles from './StageChip.module.scss'

interface Props {
  tone: ColumnTone
  children: ReactNode
}

export default function StageChip({ tone, children }: Props) {
  return <span className={[styles.chip, styles[tone]].join(' ')}>{children}</span>
}
