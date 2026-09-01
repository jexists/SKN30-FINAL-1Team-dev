// 팀 관리 표의 한 줄. 읽기만 합니다. 고치는 일은 상세 드로어가 맡습니다.
import Button from '@/components/Button'
import StatusBadge, { type StatusTone } from '@/components/StatusBadge'
import type { Role, TeamMemberRow } from '@/types'
import { wonFull } from '@/utils/format'

import styles from './MemberRow.module.scss'

interface MemberRowProps {
  member: TeamMemberRow
  /** 지금 로그인한 팀장 본인 */
  isSelf: boolean
  onOpen: () => void
}

const ROLE_LABEL: Record<Role, string> = { manager: '팀장', member: '팀원' }

// 달성률로 가르는 눈금. 팀장이 먼저 봐야 할 사람을 색으로 띄웁니다.
const HEALTHY = 70
const WATCH = 40

function health(rate: number | null): { label: string; tone: StatusTone } {
  // 목표를 세우지 않았으면 잘하고 못하고를 말할 수 없습니다.
  if (rate === null) return { label: '미설정', tone: 'neutral' }
  if (rate >= HEALTHY) return { label: '정상', tone: 'green' }
  if (rate >= WATCH) return { label: '주의', tone: 'orange' }
  return { label: '위험', tone: 'red' }
}

export default function MemberRow({ member, isSelf, onOpen }: MemberRowProps) {
  const state = health(member.achievement_rate)
  const rate = member.achievement_rate

  return (
    <tr className={member.active ? undefined : styles.isInactive}>
      <td>
        <strong className={styles.name}>{member.display_name}</strong>
        {isSelf && <span className={styles.self}>나</span>}
      </td>

      <td>{member.job_title ?? '—'}</td>

      <td>
        <StatusBadge
          label={ROLE_LABEL[member.role_code]}
          tone={member.role_code === 'manager' ? 'blue' : 'neutral'}
        />
      </td>

      <td className={`${styles.right} tnum`}>{wonFull(member.target_amount)}</td>
      <td className={`${styles.right} tnum`}>{wonFull(member.confirmed_amount)}</td>

      <td>
        <span className={styles.rate}>
          <span className="tnum">{rate === null ? '—' : `${rate}%`}</span>
          {/* 숫자 옆의 얇은 막대. 표를 훑을 때 눈으로 먼저 잡히는 것은 길이입니다. */}
          <span
            className={styles.track}
            style={{ '--p': `${Math.min(100, rate ?? 0)}%` } as React.CSSProperties}
            aria-hidden="true"
          >
            <i />
          </span>
        </span>
      </td>

      <td>
        {/* 비활성인 사람의 달성률은 말하지 않습니다. 자리를 비운 동안의 숫자입니다. */}
        {member.active ? (
          <StatusBadge label={state.label} tone={state.tone} />
        ) : (
          <StatusBadge label="비활성" />
        )}
      </td>

      <td className={styles.right}>
        <Button variant="outline" size="sm" onClick={onOpen}>
          상세
        </Button>
      </td>
    </tr>
  )
}
