// 표 셀의 표시 전용 조각들. columns.ts 가 값(정렬·검색·CSV)을 맡고
// 여기가 보이는 모양만 맡습니다.
import styles from './Customers.module.scss'

export function EmailCell({ email }: { email: string }) {
  return (
    // 줄을 누르면 상세가 열립니다. 메일은 할 일이 따로 있어 거기까지 올라가지
    // 않게 막습니다. 안 막으면 메일 앱이 뜨면서 드로어까지 같이 열립니다.
    <a
      className={styles.linkCell}
      href={`mailto:${email}`}
      onClick={(event) => event.stopPropagation()}
    >
      {email}
    </a>
  )
}

/**
 * 방문 여부. 대부분의 줄이 미방문이라 둘 다 배지로 만들면 표가 배지밭이 됩니다.
 * 뜻이 있는 쪽만 색을 갖고, 미방문은 빈 고리와 흐린 글자로 물러섭니다.
 */
export function VisitCell({ visited }: { visited: boolean }) {
  return (
    <span className={visited ? styles.visitOn : styles.visitOff}>
      <i className={styles.visitDot} aria-hidden="true" />
      {visited ? '방문' : '미방문'}
    </span>
  )
}

export function PlainNumber({ value }: { value: string }) {
  return <span className="tnum">{value}</span>
}

/**
 * 담당자가 여럿이면 대표 한 명과 나머지 수만 보여 줍니다. 좁은 칸에 이름을 다 늘어놓으면
 * 어느 것도 읽히지 않습니다. 전체 이름은 마우스를 올리면 나옵니다.
 */
export function OwnerCell({ names }: { names: string[] }) {
  if (names.length === 0) return null

  return (
    <span className={styles.ownerCell} title={names.join(', ')}>
      <span className={styles.ownerName}>{names[0]}</span>
      {names.length > 1 && <i className={styles.ownerMore}>+{names.length - 1}</i>}
    </span>
  )
}
