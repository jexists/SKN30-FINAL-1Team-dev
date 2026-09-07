import { useOwnerColor } from '@/shared/ownerColors'
import { readableInk } from '@/utils/color'

import styles from './OwnerName.module.scss'

interface Props {
  /** 담당자 이름. 비어 있으면 아무것도 세우지 않습니다. */
  name?: string | null
  /**
   * 담당자의 member id. 이 사람에게 정해 둔 색을 찾는 열쇠입니다.
   *
   * 이름으로 찾지 않는 까닭은 동명이인 때문이기도 하지만, 이름별 색을 화면에서 짜
   * 맞추면 팀장이 고른 색과 갈라지기 때문입니다. 색의 주인은 언제나 DB 입니다.
   */
  memberId?: string
  /**
   * 명부 대신 이 색으로 칠합니다. 팀 관리에서 아직 저장하지 않은 색을 미리 보여 줄 때만
   * 씁니다. 목록 화면은 넘기지 않아 언제나 저장된 값을 봅니다.
   */
  color?: string | null
}

export default function OwnerName({ name, memberId, color }: Props) {
  const stored = useOwnerColor(memberId)
  const applied = color === undefined ? stored : color
  if (!name) return null

  // 색을 정해 두지 않았으면 스타일을 얹지 않아 지금까지의 회색 그대로 섭니다.
  // 정해 두었으면 팀장이 고른 색을 그대로 칠하고 글자만 읽히는 쪽으로 뒤집습니다.
  return (
    <span
      className={styles.owner}
      style={applied === null ? undefined : { background: applied, color: readableInk(applied) }}
    >
      {name}
    </span>
  )
}
