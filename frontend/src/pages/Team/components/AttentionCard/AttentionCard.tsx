// 지금 팀장이 손봐야 할 사람만 모아 두는 카드입니다.
//
// 목록은 여덟 명이 다 같은 무게로 서 있어서, 훑지 않으면 누구부터 볼지 알 수 없습니다.
// 여기서는 갈래마다 한 줄만 두고 이름을 앞에서 셋까지 보여 준 뒤 첫 사람의 상세를 엽니다.
//
// 새로 받아 오는 값은 없습니다. 이미 화면에 있는 구성원 목록에서 추려낼 뿐입니다.
// 볼 것이 하나도 없으면 이 카드는 아예 서지 않습니다.
import type { TeamMemberRow } from '@/types'

import { WATCH } from '../../health'

import styles from './AttentionCard.module.scss'

interface Props {
  members: readonly TeamMemberRow[]
  onOpen: (memberId: string) => void
}

type Tone = 'warn' | 'bad' | 'quiet'

interface Group {
  key: string
  tone: Tone
  mark: string
  title: string
  people: readonly TeamMemberRow[]
}

/** 이름을 셋까지 늘어놓고 나머지는 수로 접습니다. */
function names(people: readonly TeamMemberRow[]): string {
  const shown = people.slice(0, 3).map((member) => member.display_name)
  const rest = people.length - shown.length
  return rest > 0 ? `${shown.join(' · ')} 외 ${rest}명` : shown.join(' · ')
}

export default function AttentionCard({ members, onOpen }: Props) {
  const active = members.filter((member) => member.active)

  const all: Group[] = [
    {
      key: 'unset',
      tone: 'warn',
      mark: '!',
      title: '목표 미설정',
      people: active.filter((member) => member.target_amount === 0),
    },
    {
      key: 'behind',
      tone: 'bad',
      mark: '↘',
      title: `달성률 ${WATCH}% 미만`,
      // 목표가 없는 사람은 위 갈래에서 이미 셉니다. 한 사람이 두 줄에 서지 않게 합니다.
      people: active.filter(
        (member) => member.achievement_rate !== null && member.achievement_rate < WATCH,
      ),
    },
    {
      key: 'inactive',
      tone: 'quiet',
      mark: '—',
      title: '비활성 구성원',
      people: members.filter((member) => !member.active),
    },
  ]

  const groups = all.filter((group) => group.people.length > 0)

  if (groups.length === 0) return null

  return (
    <section className={styles.card} aria-labelledby="team-attention-heading">
      <h2 id="team-attention-heading" className={styles.head}>
        확인이 필요한 구성원
        <span className={styles.count}>{groups.reduce((sum, g) => sum + g.people.length, 0)}</span>
      </h2>

      <ul className={styles.list}>
        {groups.map((group) => (
          <li key={group.key}>
            <button
              type="button"
              className={styles.row}
              // 여는 것은 첫 사람 하나입니다. 무엇이 열리는지 손잡이 이름으로 밝혀 둡니다.
              onClick={() => onOpen(group.people[0].id)}
            >
              <span className={`${styles.mark} ${styles[group.tone]}`} aria-hidden="true">
                {group.mark}
              </span>
              <span className={styles.body}>
                <span className={styles.title}>
                  {group.title} {group.people.length}명
                </span>
                <span className={styles.names}>{names(group.people)}</span>
              </span>
              <span className={styles.action}>{group.people[0].display_name} 열기</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
