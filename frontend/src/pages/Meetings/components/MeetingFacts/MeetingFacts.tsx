// 미팅 상대와 자리에 대한 사실입니다. 작성 화면과 상세가 같은 것을 봅니다.
// 값은 일정에서 왔고 여기서 고치지 않습니다. 일정이 틀렸다면 캘린더에서 고칠 일입니다.
import styles from './MeetingFacts.module.scss'

interface Props {
  dept: string
  contact: string
  product: string
  place: string
  /**
   * 작성 화면은 머리말에서 회사·일시를 빼고 여기서 한 번만 보여 줍니다.
   * 상세 화면은 머리말에 그대로 두므로 넘기지 않습니다.
   *
   * 넘긴 이상 값이 비어도 칸은 남깁니다. 회사가 조용히 사라지면 빠진 것인지
   * 원래 없는 것인지 알 수 없습니다.
   */
  hospital?: string
  when?: string
}

export default function MeetingFacts({ dept, contact, product, place, hospital, when }: Props) {
  const facts: [string, string][] = [
    ...(hospital === undefined ? [] : ([['회사', hospital]] as [string, string][])),
    ['부서', dept],
    ['담당자', contact],
    ['제품', product],
    ['장소', place],
    ...(when === undefined ? [] : ([['일시', when]] as [string, string][])),
  ]

  return (
    <dl className={styles.facts}>
      {facts.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          {/* 일정에 비어 있는 칸이 있습니다. 빈 줄을 두면 값이 사라진 것처럼 보입니다. */}
          <dd>{value.trim() || '—'}</dd>
        </div>
      ))}
    </dl>
  )
}
