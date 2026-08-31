// 팀원 한 명의 상세. 인사 정보와 그달 매출 목표를 여기서 고칩니다.
//
// 이름과 이메일은 Supabase Auth 가 가진 값이라 읽기만 합니다. 계정 자체를 만드는 일은
// 어드민 화면(/admin)의 몫이고, 이 화면은 이미 있는 사람의 역할과 목표를 다룹니다.
//
// 목표는 월 하나만 저장합니다(sales_target 이 월 단위입니다). 분기·연간은 팀장이 감을
// 잡으라고 환산해 보여 줄 뿐이라 입력칸을 두지 않습니다. 넣을 수 있게 해 두면 저장되지
// 않는 칸이 되어 오히려 헷갈립니다.
import { useState } from 'react'

import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import FormField from '@/components/FormField'
import StatusBadge from '@/components/StatusBadge'
import { errorMessage } from '@/api/errorMessage'
import { showToast } from '@/shared/toast'
import type { Role, TeamMemberPatchRequest, TeamMemberRow } from '@/types'
import { wonFull } from '@/utils/format'

import styles from './MemberDrawer.module.scss'

interface Props {
  member: TeamMemberRow
  /** 지금 로그인한 팀장 본인인지. 자기 역할과 재직 상태는 스스로 바꾸지 못합니다. */
  isSelf: boolean
  targetMonth: string
  onSave: (memberId: string, patch: TeamMemberPatchRequest) => Promise<unknown>
  onClose: () => void
}

const ROLE_LABEL: Record<Role, string> = { manager: '팀장', member: '팀원' }

export default function MemberDrawer({ member, isSelf, targetMonth, onSave, onClose }: Props) {
  const [jobTitle, setJobTitle] = useState(member.job_title ?? '')
  const [role, setRole] = useState<Role>(member.role_code)
  const [active, setActive] = useState(member.active)
  const [monthlyTarget, setMonthlyTarget] = useState(member.target_amount)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const dirty =
    jobTitle !== (member.job_title ?? '') ||
    role !== member.role_code ||
    active !== member.active ||
    monthlyTarget !== member.target_amount

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const patch: TeamMemberPatchRequest = { monthly_target_amount: monthlyTarget }
      // 직함은 비울 수 없습니다. 서버가 빈 문자열을 거절하므로 바뀐 값만 보냅니다.
      if (jobTitle.trim() !== '' && jobTitle !== (member.job_title ?? '')) {
        patch.job_title = jobTitle.trim()
      }
      if (role !== member.role_code) patch.role_code = role
      if (active !== member.active) patch.active = active
      await onSave(member.id, patch)
      showToast(`${member.display_name} 님의 정보를 저장했습니다.`)
      onClose()
    } catch (caught: unknown) {
      setError(errorMessage(caught, '저장하지 못했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Drawer
      title={member.display_name}
      sub={member.email ?? '이메일 없음'}
      meta={
        <>
          <StatusBadge label={ROLE_LABEL[member.role_code]} tone={role === 'manager' ? 'blue' : 'neutral'} />
          <StatusBadge
            label={member.active ? '재직' : '비활성'}
            tone={member.active ? 'green' : 'neutral'}
          />
        </>
      }
      footer={
        <>
          <Button variant="outline" disabled={saving} onClick={onClose}>
            취소
          </Button>
          <Button disabled={!dirty || saving} onClick={() => void save()}>
            {saving ? '저장 중…' : '저장'}
          </Button>
        </>
      }
      onClose={onClose}
    >
      <section className={styles.section}>
        <h3 className={styles.heading}>기본 정보</h3>
        <dl className={styles.facts}>
          <div>
            <dt>이름</dt>
            <dd>{member.display_name}</dd>
          </div>
          <div>
            <dt>이메일</dt>
            <dd>{member.email ?? '—'}</dd>
          </div>
        </dl>

        <div className={styles.fields}>
          <FormField label="직책">
            <input
              className={styles.input}
              value={jobTitle}
              placeholder="영업 담당자"
              onChange={(event) => setJobTitle(event.target.value)}
            />
          </FormField>

          <FormField label="역할">
            <select
              className={styles.input}
              value={role}
              // 팀장이 자기 역할을 내리면 이 화면에 다시 들어올 수 없습니다.
              disabled={isSelf}
              onChange={(event) => setRole(event.target.value as Role)}
            >
              <option value="manager">{ROLE_LABEL.manager}</option>
              <option value="member">{ROLE_LABEL.member}</option>
            </select>
          </FormField>

          <FormField label="계정 상태">
            <select
              className={styles.input}
              value={active ? 'active' : 'inactive'}
              disabled={isSelf}
              onChange={(event) => setActive(event.target.value === 'active')}
            >
              <option value="active">재직</option>
              <option value="inactive">비활성</option>
            </select>
          </FormField>
        </div>
        {isSelf && (
          <p className={styles.hint}>
            자기 역할과 계정 상태는 바꿀 수 없습니다. 팀에 팀장이 없어지면 이 화면에 다시 들어올
            수 없습니다.
          </p>
        )}
      </section>

      <section className={styles.section}>
        <h3 className={styles.heading}>목표 매출</h3>
        <div className={styles.fields}>
          <FormField label={`월 목표 (${targetMonth})`}>
            <input
              type="number"
              className={`${styles.input} tnum`}
              value={monthlyTarget}
              min={0}
              step={1_000_000}
              onChange={(event) => setMonthlyTarget(Math.max(0, Number(event.target.value)))}
            />
          </FormField>
        </div>
        <p className={styles.amount}>{wonFull(monthlyTarget)}</p>

        {/* 저장하는 값은 월 목표 하나입니다. 아래 둘은 읽기 전용 환산값입니다. */}
        <dl className={styles.facts}>
          <div>
            <dt>분기 목표</dt>
            <dd className="tnum">{wonFull(monthlyTarget * 3)}</dd>
          </div>
          <div>
            <dt>연간 목표</dt>
            <dd className="tnum">{wonFull(monthlyTarget * 12)}</dd>
          </div>
        </dl>
        <p className={styles.hint}>
          분기·연간은 월 목표를 3배·12배로 환산한 값입니다. 저장되는 것은 월 목표뿐입니다.
        </p>
      </section>

      <section className={styles.section}>
        <h3 className={styles.heading}>이달 실적</h3>
        <dl className={styles.facts}>
          <div>
            <dt>현재 매출</dt>
            <dd className="tnum">{wonFull(member.confirmed_amount)}</dd>
          </div>
          <div>
            <dt>달성률</dt>
            <dd className="tnum">
              {member.achievement_rate === null ? '목표 미설정' : `${member.achievement_rate}%`}
            </dd>
          </div>
        </dl>
      </section>

      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </Drawer>
  )
}
