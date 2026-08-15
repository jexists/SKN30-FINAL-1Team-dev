// 단계 진행 막대. 점과 선으로 단계를 세우고, 칸마다 지금 몇 건이 걸려 있는지를 답니다.
//
// 계약과 발주가 같은 모양을 써야 해서 공용에 둡니다. 단계 이름은 각 도메인이
// 정하고(board.ts / pipeline.ts) 여기는 그리기만 합니다.
//
// 점은 칸 안에 가운데로 두지 않고 첫 점을 0%, 끝 점을 100% 에 박습니다. 그래야
// 칸 수가 다른 막대(계약 7칸, 발주 5칸)를 위아래로 놓아도 양 끝이 맞습니다.
//
// 건이 없는 칸은 누를 것이 없어 버튼을 죽입니다. 눌러도 아무것도 안 열리면
// 고장으로 읽히기 때문입니다.
import styles from './StageBar.module.scss'

interface Props {
  steps: string[]
  /** 칸마다 걸린 건수. steps 와 길이가 같아야 합니다. */
  counts: number[]
  /** 펼친 칸. -1 이면 접힌 상태입니다. */
  selected: number
  onSelect: (index: number) => void
  label: string
}

export default function StageBar({ steps, counts, selected, onSelect, label }: Props) {
  const last = steps.length - 1

  return (
    <ul
      className={styles.bar}
      style={{ '--n': last || 1 } as React.CSSProperties}
      aria-label={label}
    >
      {steps.map((step, index) => {
        const count = counts[index] ?? 0
        return (
          <li
            key={step}
            className={[
              styles.step,
              count > 0 ? styles.hasAny : '',
              index === selected ? styles.isOpen : '',
              index === 0 ? styles.first : '',
              index === last ? styles.last : '',
            ]
              .filter(Boolean)
              .join(' ')}
            style={{ '--i': index } as React.CSSProperties}
          >
            <button
              type="button"
              disabled={count === 0}
              aria-expanded={count > 0 ? index === selected : undefined}
              onClick={() => onSelect(index === selected ? -1 : index)}
            >
              <i aria-hidden="true" />
              <span className={styles.name}>{step}</span>
              <span className={`${styles.count} tnum`}>{count}건</span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
