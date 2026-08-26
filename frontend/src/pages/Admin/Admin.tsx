// 계정 발급. 어드민이 팀과 구성원 정보를 넣으면 Supabase 사용자 생성·초대 메일·
// team/member 등록이 한 번에 끝납니다.
//
// 비밀번호 입력란이 없습니다. 초대 메일을 받은 사람이 직접 정하므로 발급하는 쪽이
// 비밀번호를 알 방법도, 전달할 이유도 없습니다.
//
// 로컬에서만 "바로 만들기"를 고를 수 있습니다. 메일을 받을 곳이 없을 때 쓰라고
// 서버가 초대를 건너뛰고 비밀번호를 LOCAL_DEV_PASSWORD 로 고정합니다
// (backend/app/api/admin.py). 고르지 않으면 로컬에서도 초대 메일이 나갑니다.
import { type FormEvent, useCallback, useEffect, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import Button from '@/components/Button'
import { env } from '@/config/env'

import styles from './Admin.module.scss'

interface AdminTeamMember {
  id: string
  display_name: string
  email: string | null
  role_code: 'member' | 'manager'
  active: boolean
}

interface AdminTeam {
  id: string
  name: string
  company_name: string | null
  department: string | null
  business_no: string | null
  member_count: number
  members: AdminTeamMember[]
}

/** 팀 선택란의 "새 팀 만들기" 항목. 실제 팀 id 와 섞이지 않는 값을 씁니다. */
const NEW_TEAM = 'new'

/** 로컬에서 서버가 고정으로 넣는 비밀번호. backend/app/api/admin.py 의 값과 같아야 합니다. */
const LOCAL_DEV_PASSWORD = '12341234'

/** 표시용으로만 하이픈을 넣습니다. 서버에는 숫자 10자리로 저장됩니다. */
function formatBusinessNo(value: string | null): string {
  if (value === null || value.length !== 10) return value ?? '-'
  return `${value.slice(0, 3)}-${value.slice(3, 5)}-${value.slice(5)}`
}

export default function Admin() {
  const [teams, setTeams] = useState<AdminTeam[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  const [teamChoice, setTeamChoice] = useState<string>(NEW_TEAM)
  const [teamName, setTeamName] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [department, setDepartment] = useState('')
  const [businessNo, setBusinessNo] = useState('')

  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [roleCode, setRoleCode] = useState<'member' | 'manager'>('member')
  // 로컬에서만 고를 수 있습니다. 서버도 local 이 아니면 instant 를 거절합니다.
  const [instant, setInstant] = useState(false)

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const loadTeams = useCallback(async () => {
    try {
      const { data } = await client.get<AdminTeam[]>('/admin/teams')
      setTeams(data)
      setLoadError(null)
    } catch (cause) {
      setLoadError(errorMessage(cause, '팀 목록을 불러올 수 없습니다.'))
    }
  }, [])

  useEffect(() => {
    void loadTeams()
  }, [loadTeams])

  const creatingTeam = teamChoice === NEW_TEAM
  // 발급 방식을 고르는 칸은 로컬에서만 그리므로 배포본에서는 항상 초대 메일입니다.
  const issuingInstantly = env.isDev && instant

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    setNotice(null)

    const payload = {
      email: email.trim(),
      display_name: displayName.trim(),
      role_code: roleCode,
      instant: issuingInstantly,
      ...(creatingTeam
        ? {
            team: {
              name: teamName.trim(),
              company_name: companyName.trim() || null,
              department: department.trim() || null,
              business_no: businessNo.trim() || null,
            },
          }
        : { team_id: teamChoice }),
    }

    try {
      await client.post('/admin/accounts', payload)
      setNotice(
        issuingInstantly
          ? `${email.trim()} 계정을 만들었습니다. 비밀번호는 ${LOCAL_DEV_PASSWORD} 입니다.`
          : `${email.trim()} 으로 초대 메일을 보냈습니다.`,
      )
      // 방금 만든 계정이 목록에 뜨는 것으로 발급을 확인시킵니다.
      await loadTeams()
      setEmail('')
      setDisplayName('')
      if (creatingTeam) {
        setTeamName('')
        setCompanyName('')
        setDepartment('')
        setBusinessNo('')
      }
    } catch (cause) {
      setError(errorMessage(cause, '계정을 발급할 수 없습니다. 잠시 후 다시 시도해 주세요.'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className={styles.page}>
      <h1 className="sr-only">계정 발급</h1>

      <form className={styles.card} onSubmit={onSubmit}>
        <h2 className={styles.cardTitle}>새 계정 발급</h2>

        <div className={styles.field}>
          <label htmlFor="team">팀</label>
          <select
            className={styles.input}
            id="team"
            value={teamChoice}
            onChange={(e) => setTeamChoice(e.target.value)}
            disabled={submitting}
          >
            <option value={NEW_TEAM}>+ 새 팀 만들기</option>
            {teams.map((team) => (
              <option key={team.id} value={team.id}>
                {team.name}
                {team.company_name ? ` · ${team.company_name}` : ''} ({team.member_count}명)
              </option>
            ))}
          </select>
        </div>

        {creatingTeam && (
          <fieldset className={styles.group}>
            <legend>새 팀 정보</legend>

            <div className={styles.field}>
              <label htmlFor="team-name">팀명</label>
              <input
                className={styles.input}
                id="team-name"
                value={teamName}
                onChange={(e) => setTeamName(e.target.value)}
                disabled={submitting}
                required
              />
            </div>

            <div className={styles.row}>
              <div className={styles.field}>
                <label htmlFor="company-name">회사명</label>
                <input
                  className={styles.input}
                  id="company-name"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  disabled={submitting}
                />
              </div>

              <div className={styles.field}>
                <label htmlFor="department">부서명</label>
                <input
                  className={styles.input}
                  id="department"
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                  disabled={submitting}
                />
              </div>
            </div>

            <div className={styles.field}>
              <label htmlFor="business-no">사업자등록번호</label>
              <input
                className={styles.input}
                id="business-no"
                inputMode="numeric"
                placeholder="000-00-00000"
                value={businessNo}
                onChange={(e) => setBusinessNo(e.target.value)}
                disabled={submitting}
              />
              <p className={styles.hint}>하이픈은 넣어도 되고 빼도 됩니다.</p>
            </div>
          </fieldset>
        )}

        <fieldset className={styles.group}>
          <legend>구성원</legend>

          <div className={styles.row}>
            <div className={styles.field}>
              <label htmlFor="email">이메일</label>
              <input
                className={styles.input}
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={submitting}
                required
              />
            </div>

            <div className={styles.field}>
              <label htmlFor="display-name">이름</label>
              <input
                className={styles.input}
                id="display-name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                disabled={submitting}
                required
              />
            </div>
          </div>

          <div className={styles.field}>
            <span className={styles.label}>역할</span>
            <div className={styles.choices}>
              <label className={styles.choice}>
                <input
                  type="radio"
                  name="role"
                  value="member"
                  checked={roleCode === 'member'}
                  onChange={() => setRoleCode('member')}
                  disabled={submitting}
                />
                팀원
              </label>
              <label className={styles.choice}>
                <input
                  type="radio"
                  name="role"
                  value="manager"
                  checked={roleCode === 'manager'}
                  onChange={() => setRoleCode('manager')}
                  disabled={submitting}
                />
                팀장
              </label>
            </div>
          </div>

          {env.isDev && (
            <div className={styles.field}>
              <span className={styles.label}>발급 방식</span>
              <div className={styles.choices}>
                <label className={styles.choice}>
                  <input
                    type="radio"
                    name="issue"
                    value="invite"
                    checked={!instant}
                    onChange={() => setInstant(false)}
                    disabled={submitting}
                  />
                  초대 메일로 만들기
                </label>
                <label className={styles.choice}>
                  <input
                    type="radio"
                    name="issue"
                    value="instant"
                    checked={instant}
                    onChange={() => setInstant(true)}
                    disabled={submitting}
                  />
                  바로 만들기 (비밀번호 {LOCAL_DEV_PASSWORD})
                </label>
              </div>
            </div>
          )}
        </fieldset>

        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        {notice && (
          <p className={styles.notice} role="status">
            {notice}
          </p>
        )}

        <Button type="submit" disabled={submitting}>
          {submitting ? '발급 중…' : '계정 발급'}
        </Button>
        <p className={styles.hint}>
          {issuingInstantly
            ? `메일 없이 비밀번호 ${LOCAL_DEV_PASSWORD} 로 바로 만듭니다. 로컬에서만 됩니다.`
            : '비밀번호는 여기서 정하지 않습니다. 초대 메일을 받은 사람이 직접 정합니다.'}
        </p>
      </form>

      <div className={styles.card}>
        <h2 className={styles.cardTitle}>등록된 팀</h2>

        {loadError && (
          <p className={styles.error} role="alert">
            {loadError}
          </p>
        )}

        {!loadError && teams.length === 0 && (
          <p className={styles.hint}>아직 등록된 팀이 없습니다.</p>
        )}

        {teams.map((team) => (
          <article key={team.id} className={styles.team}>
            <header className={styles.teamHead}>
              <strong>{team.name}</strong>
              <span className={styles.meta}>
                {[team.company_name, team.department].filter(Boolean).join(' · ') || '-'} ·
                사업자등록번호 {formatBusinessNo(team.business_no)}
              </span>
            </header>

            <ul className={styles.members}>
              {team.members.map((member) => (
                <li key={member.id}>
                  <span>{member.display_name}</span>
                  <span className={styles.meta}>{member.email ?? '-'}</span>
                  <span className={styles.meta}>
                    {member.role_code === 'manager' ? '팀장' : '팀원'}
                    {member.active ? '' : ' · 비활성'}
                  </span>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  )
}
