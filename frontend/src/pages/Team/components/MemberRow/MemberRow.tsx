import Button from '@/components/Button'
import type { Role } from '@/types'
import type { TeamMember } from '@/types'
import { wonFull } from '@/utils/format'

import styles from './MemberRow.module.scss'

interface MemberRowProps {
  member: TeamMember
  /** 지금 로그인한 팀장 본인. 자기 역할은 스스로 내리지 못하게 합니다. */
  isSelf: boolean
  dirty: boolean
  onEdit: (patch: Partial<TeamMember>) => void
  onSave: () => void
  onCancel: () => void
}

const ROLE_LABEL: Record<Role, string> = { manager: '팀장', member: '팀원' }

export default function MemberRow({
  member,
  isSelf,
  dirty,
  onEdit,
  onSave,
  onCancel,
}: MemberRowProps) {
  return (
    <tr className={dirty ? styles.isDirty : undefined}>
      <td>
        <strong className={styles.name}>{member.name}</strong>
        {isSelf && <span className={styles.self}>나</span>}
      </td>

      <td>
        <input
          className={styles.text}
          value={member.title}
          aria-label={`${member.name} 직함`}
          onChange={(event) => onEdit({ title: event.target.value })}
        />
      </td>

      <td>
        <select
          className={styles.select}
          value={member.role}
          aria-label={`${member.name} 역할`}
          // 팀장이 자기 역할을 팀원으로 내리면 이 화면에 다시 들어올 수 없습니다.
          disabled={isSelf}
          onChange={(event) => onEdit({ role: event.target.value as Role })}
        >
          <option value="manager">{ROLE_LABEL.manager}</option>
          <option value="member">{ROLE_LABEL.member}</option>
        </select>
      </td>

      <td>
        <label className={styles.switch}>
          <input
            type="checkbox"
            checked={member.active}
            onChange={(event) => onEdit({ active: event.target.checked })}
          />
          {member.active ? '재직' : '비활성'}
        </label>
      </td>

      <td className={styles.right}>
        <input
          type="number"
          className={`${styles.number} tnum`}
          value={member.monthlyTarget}
          min={0}
          step={1_000_000}
          aria-label={`${member.name} 월 매출 목표(원)`}
          onChange={(event) => onEdit({ monthlyTarget: Math.max(0, Number(event.target.value)) })}
        />
        <span className={styles.hint}>{wonFull(member.monthlyTarget)}</span>
      </td>

      <td className={styles.right}>
        {dirty && (
          <span className={styles.actions}>
            <Button variant="ghost" onClick={onCancel}>
              취소
            </Button>
            <Button onClick={onSave}>저장</Button>
          </span>
        )}
      </td>
    </tr>
  )
}
