import styles from './Scrim.module.scss'

/**
 * 모바일 드로어 뒤를 덮는 배경.
 *
 * 클릭으로 닫는 것은 포인터 사용자를 위한 지름길입니다. 키보드로는 Escape 와
 * 드로어 안의 닫기 버튼을 쓰므로 여기에 포커스를 두지 않습니다.
 */
export default function Scrim({ onClick }: { onClick: () => void }) {
  return <div className={styles.scrim} onClick={onClick} aria-hidden="true" />
}
