import styles from './OwnerName.module.scss'

interface Props {
  /** 담당자 이름. 비어 있으면 아무것도 세우지 않습니다. */
  name?: string | null
}

/**
 * 이 줄이 누구 것인지 알리는 이름표입니다.
 *
 * 아바타를 두지 않습니다. 여기서 알아야 하는 것은 "누구"이지 "누구의 얼굴"이 아니고,
 * 팀 하나가 한 화면에 다 들어오는 규모라 이름 넉 자면 충분합니다.
 *
 * 세울지 말지는 부르는 쪽이 useShowOwner() 로 정합니다. 여기서 다시 묻지 않는 까닭은
 * 이 이름표가 목록 줄에도 서고 카드 아래에도 서기 때문입니다.
 *
 * 표 안에서는 쓰지 않습니다. 표의 담당자 칸은 DataColumn.text() 가 정렬·검색·CSV 를
 * 함께 먹이므로 그쪽 규칙을 따릅니다. 이 이름표는 표 바깥 표면에만 씁니다.
 */
export default function OwnerName({ name }: Props) {
  if (!name) return null
  return <span className={styles.owner}>{name}</span>
}
