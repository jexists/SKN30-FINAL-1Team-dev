// 팀 관리 표의 한 줄. 읽기만 합니다. 고치는 일은 상세 드로어가 맡습니다.
//
// 다른 목록(고객·자료실·고객불만)과 같이 줄 아무 곳이나 눌러 상세를 엽니다. 줄은 초점을
// 받지 못하므로 이름 칸에 키보드용 손잡이를 하나 둡니다.
//
// 한 사람에 대한 여덟 칸을 다섯으로 묶었습니다. 직책·지역처럼 자주 비는 값은 제 칸을
// 가지면 표가 '—' 로 덮이므로, 있을 때만 이름·역할 옆에 붙는 곁줄로 둡니다.
import StatusBadge from '@/components/StatusBadge'
import { useOwnerColor } from '@/shared/ownerColors'
import { regionLabel } from '@/shared/regionCodes'
import type { Role, TeamMemberRow } from '@/types'
import { readableInk } from '@/utils/color'
import { wonFull } from '@/utils/format'

import { health } from '../../health'

import styles from './MemberRow.module.scss'

interface MemberRowProps {
  member: TeamMemberRow
  /** 지금 로그인한 팀장 본인 */
  isSelf: boolean
  onOpen: () => void
}

const ROLE_LABEL: Record<Role, string> = { manager: '팀장', member: '팀원' }

export default function MemberRow({ member, isSelf, onOpen }: MemberRowProps) {
  // 색의 주인은 언제나 DB 입니다. 이름에서 색을 지어내지 않습니다.
  const color = useOwnerColor(member.id)
  const state = health(member.achievement_rate)
  const rate = member.achievement_rate
  const region = member.region_code === null ? null : regionLabel(member.region_code)

  return (
    <tr
      className={`${styles.clickable} ${member.active ? '' : styles.isInactive}`}
      onClick={onOpen}
    >
      <td>
        <span className={styles.person}>
          {/* 색을 정해 두지 않았으면 회색 그대로 섭니다. */}
          <span
            className={styles.avatar}
            style={color === null ? undefined : { background: color, color: readableInk(color) }}
            aria-hidden="true"
          >
            {member.display_name.trim().slice(0, 1)}
          </span>
          <span className={styles.identity}>
            <span className={styles.nameLine}>
              <button
                type="button"
                className={styles.openButton}
                onClick={(event) => {
                  event.stopPropagation()
                  onOpen()
                }}
              >
                {member.display_name}
              </button>
              {isSelf && <span className={styles.self}>나</span>}
            </span>
            {member.job_title !== null && <span className={styles.job}>{member.job_title}</span>}
          </span>
        </span>
      </td>

      <td>
        <span className={styles.role}>
          <StatusBadge
            label={ROLE_LABEL[member.role_code]}
            tone={member.role_code === 'manager' ? 'blue' : 'neutral'}
          />
          {region !== null && <span className={styles.region}>{region}</span>}
        </span>
      </td>

      <td className={styles.progressCell}>
        {member.target_amount === 0 ? (
          // 목표가 없는 사람에게 '₩0 / ₩0' 은 아무것도 알려 주지 않습니다.
          <span className={`${styles.amounts} tnum`}>{wonFull(member.confirmed_amount)}</span>
        ) : (
          <>
            <span className={`${styles.amounts} tnum`}>
              {wonFull(member.confirmed_amount)} <em>/ {wonFull(member.target_amount)}</em>
            </span>
            {/* 표를 훑을 때 눈으로 먼저 잡히는 것은 숫자가 아니라 길이입니다. */}
            <span
              className={styles.track}
              style={{ '--p': `${Math.min(100, rate ?? 0)}%` } as React.CSSProperties}
              aria-hidden="true"
            >
              <i />
            </span>
          </>
        )}
      </td>

      <td className={styles.right}>
        {/* 목표가 없으면 달성률도 없습니다. 무엇을 해야 하는지는 위 카드가 한 번만 말합니다.
            여기까지 파란 손잡이를 두면 여덟 줄이 전부 손잡이가 되어 진짜 할 일이 묻힙니다. */}
        {rate === null ? (
          <span className={styles.blank}>—</span>
        ) : (
          <span className="tnum">{rate}%</span>
        )}
      </td>

      <td>
        {/* 비활성인 사람의 달성률은 말하지 않습니다. 자리를 비운 동안의 숫자입니다. */}
        {member.active ? (
          <StatusBadge label={state.label} tone={state.tone} />
        ) : (
          <StatusBadge label="비활성" />
        )}
      </td>
    </tr>
  )
}
