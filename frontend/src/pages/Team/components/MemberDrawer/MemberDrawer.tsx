// 팀원 한 명의 상세. 인사 정보와 그달 매출 목표를 여기서 고칩니다.
//
// 이름과 이메일은 Supabase Auth 가 가진 값이라 읽기만 합니다. 계정 자체를 만드는 일은
// 어드민 화면(/admin)의 몫이고, 이 화면은 이미 있는 사람의 역할과 목표를 다룹니다.
//
// 목표는 월 하나만 저장합니다(sales_target 이 월 단위입니다). 분기·연간은 팀장이 감을
// 잡으라고 환산해 보여 줄 뿐이라 입력칸을 두지 않습니다. 넣을 수 있게 해 두면 저장되지
// 않는 칸이 되어 오히려 헷갈립니다.
import { useCallback, useEffect, useState } from 'react'

import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import FormField from '@/components/FormField'
import OwnerName from '@/components/OwnerName'
import Select from '@/components/Select'
import StatusBadge from '@/components/StatusBadge'
import { errorMessage } from '@/api/errorMessage'
import { REGION_OPTIONS } from '@/shared/regionCodes'
import { showToast } from '@/shared/toast'
import type { HandoverCounts, Role, TeamMemberPatchRequest, TeamMemberRow } from '@/types'
import { wonFull } from '@/utils/format'

import styles from './MemberDrawer.module.scss'

interface Props {
  member: TeamMemberRow
  /** 팀 전체. 담당 데이터를 넘겨받을 사람을 여기서 고릅니다. */
  members: TeamMemberRow[]
  /** 지금 로그인한 팀장 본인인지. 자기 역할과 재직 상태는 스스로 바꾸지 못합니다. */
  isSelf: boolean
  targetMonth: string
  onSave: (memberId: string, patch: TeamMemberPatchRequest) => Promise<unknown>
  onLoadHandover: (memberId: string) => Promise<HandoverCounts>
  onHandover: (fromId: string, toId: string) => Promise<HandoverCounts>
  onClose: () => void
}

const ROLE_LABEL: Record<Role, string> = { manager: '팀장', member: '팀원' }
const ROLE_OPTIONS = [
  { value: 'manager', label: ROLE_LABEL.manager },
  { value: 'member', label: ROLE_LABEL.member },
]
const ACTIVE_OPTIONS = [
  { value: 'active', label: '재직' },
  { value: 'inactive', label: '비활성' },
]

/** 색을 정하지 않았을 때 견본이 보여 줄 색. 회색 이름표(--fill)와 같은 자리입니다. */
const DEFAULT_SWATCH = '#e3e3e5'
const HEX = /^#[0-9a-fA-F]{6}$/
const COLOR_ERROR = '#RRGGBB 형식으로 적어 주세요.'

/** 이관 대상. 서버가 세는 네 가지와 같은 순서입니다. */
const HANDOVER_LABEL: Record<keyof HandoverCounts, string> = {
  customer_contacts: '거래처',
  sales_deals: '딜',
  activities: '일정',
  support_requests: '고객불만',
}

export default function MemberDrawer({
  member,
  members,
  isSelf,
  targetMonth,
  onSave,
  onLoadHandover,
  onHandover,
  onClose,
}: Props) {
  const [jobTitle, setJobTitle] = useState(member.job_title ?? '')
  const [role, setRole] = useState<Role>(member.role_code)
  const [active, setActive] = useState(member.active)
  // 빈 문자열이 '담당지역 미지정' 입니다. 선택란의 첫 항목이 이 값입니다.
  const [region, setRegion] = useState(member.region_code ?? '')
  const [monthlyTarget, setMonthlyTarget] = useState(member.target_amount)
  // 빈 문자열이 '색 미지정' 입니다. 손으로 적는 칸이 있어 저장 못 할 값도 잠시 머뭅니다.
  const [color, setColor] = useState(member.badge_color ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // 넘길 담당 데이터의 수. 아직 세지 않았으면 null 입니다.
  const [counts, setCounts] = useState<HandoverCounts | null>(null)
  const [heir, setHeir] = useState('')
  const [moving, setMoving] = useState(false)

  const countHandover = useCallback(() => {
    void onLoadHandover(member.id)
      .then(setCounts)
      // 건수를 못 세도 드로어의 나머지는 쓸 수 있어야 합니다. 이관 칸만 비워 둡니다.
      .catch(() => setCounts(null))
  }, [member.id, onLoadHandover])

  useEffect(() => {
    // 이관 칸이 보일 때만 셉니다. 자기 자신은 비활성으로 내릴 수 없어 그 칸이 없습니다.
    if (!isSelf && !active) countHandover()
  }, [isSelf, active, countHandover])

  // 인계자는 재직 중인 다른 팀원뿐입니다. 비활성인 사람에게 넘기면 그대로 또 사라집니다.
  const heirOptions = [
    { value: '', label: '선택' },
    ...members
      .filter((row) => row.active && row.id !== member.id)
      .map((row) => ({ value: row.id, label: row.display_name })),
  ]
  const total =
    counts === null
      ? 0
      : counts.customer_contacts + counts.sales_deals + counts.activities + counts.support_requests

  const moveWork = async () => {
    setMoving(true)
    setError(null)
    try {
      const moved = await onHandover(member.id, heir)
      const name = members.find((row) => row.id === heir)?.display_name ?? '다른 팀원'
      const movedTotal =
        moved.customer_contacts + moved.sales_deals + moved.activities + moved.support_requests
      showToast(`${movedTotal}건을 ${name} 님에게 넘겼습니다.`)
      setHeir('')
      countHandover()
    } catch (caught: unknown) {
      setError(errorMessage(caught, '이관하지 못했습니다.'))
    } finally {
      setMoving(false)
    }
  }

  const colorValid = color === '' || HEX.test(color)
  // 저장될 값입니다. 표기만 소문자로 맞추고 색 자체는 손대지 않습니다.
  const nextColor = colorValid && color !== '' ? color.toLowerCase() : null
  const savedColor = member.badge_color ?? null
  // 색과 같이 null 이 '지운다' 입니다.
  const nextRegion = region === '' ? null : region
  const savedRegion = member.region_code ?? null

  const dirty =
    jobTitle !== (member.job_title ?? '') ||
    role !== member.role_code ||
    active !== member.active ||
    nextRegion !== savedRegion ||
    nextColor !== savedColor ||
    monthlyTarget !== member.target_amount

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      // 바뀐 값만 보냅니다. 역할만 고쳐 저장할 때 목표까지 실어 보내면 그사이 다른
      // 곳에서 바뀐 목표를 열었을 때의 값으로 되돌립니다.
      const patch: TeamMemberPatchRequest = {}
      if (monthlyTarget !== member.target_amount) patch.monthly_target_amount = monthlyTarget
      // 직함은 비울 수 없습니다. 서버가 빈 문자열을 거절하므로 바뀐 값만 보냅니다.
      if (jobTitle.trim() !== '' && jobTitle !== (member.job_title ?? '')) {
        patch.job_title = jobTitle.trim()
      }
      if (role !== member.role_code) patch.role_code = role
      if (active !== member.active) patch.active = active
      // null 이 '담당지역을 미지정으로' 입니다.
      if (nextRegion !== savedRegion) patch.region_code = nextRegion
      // null 이 '색을 지우고 기본 회색으로' 입니다. 서버도 여기서만 null 을 받습니다.
      if (nextColor !== savedColor) patch.badge_color = nextColor
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
          <StatusBadge
            label={ROLE_LABEL[member.role_code]}
            tone={role === 'manager' ? 'blue' : 'neutral'}
          />
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
          <Button disabled={!dirty || !colorValid || saving} onClick={() => void save()}>
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

          <FormField label="역할" htmlFor={false}>
            <Select
              label="역할"
              value={role}
              options={ROLE_OPTIONS}
              // 팀장이 자기 역할을 내리면 이 화면에 다시 들어올 수 없습니다.
              disabled={isSelf}
              onChange={(next) => setRole(next as Role)}
            />
          </FormField>

          {/* 맡은 지역. 고객사 지역과 같은 코드를 쓰므로 손으로 적지 않고 고릅니다. */}
          <FormField label="담당지역" htmlFor={false}>
            <Select label="담당지역" value={region} options={REGION_OPTIONS} onChange={setRegion} />
          </FormField>

          <FormField label="계정 상태" htmlFor={false}>
            <Select
              label="계정 상태"
              value={active ? 'active' : 'inactive'}
              options={ACTIVE_OPTIONS}
              disabled={isSelf}
              onChange={(next) => setActive(next === 'active')}
            />
          </FormField>

          {/* 색은 목록에서 담당자를 가르는 표시라 인사 정보와 함께 둡니다. 고른 색을 연하게
              바꾸지 않고 그대로 씁니다. 읽히지 않을 만큼 어두우면 글자만 흰색이 됩니다. */}
          <FormField label="담당자 색상" error={colorValid ? undefined : COLOR_ERROR}>
            <div className={styles.colorRow}>
              <input
                type="color"
                className={styles.swatch}
                // 색을 정하지 않았으면 견본도 기본 회색을 보여 줍니다. 여기만 다른 색을
                // 세워 두면 '미지정' 이라 적힌 옆에서 색이 정해진 것처럼 보입니다.
                value={nextColor ?? DEFAULT_SWATCH}
                aria-label="담당자 색상 고르기"
                onChange={(event) => setColor(event.target.value)}
              />
              <input
                className={styles.input}
                value={color}
                placeholder="미지정"
                aria-label="담당자 색상 HEX 값"
                spellCheck={false}
                onChange={(event) => {
                  const typed = event.target.value.trim()
                  // '#' 을 빼고 적는 사람이 많습니다. 비어 있을 때는 붙이지 않아야 지울 수 있습니다.
                  setColor(typed === '' || typed.startsWith('#') ? typed : `#${typed}`)
                }}
              />
            </div>
          </FormField>
        </div>

        {/* 목표 매출의 환산 안내와 같은 자리, 같은 크기입니다. 이름표를 문장 안에 세워 두면
            무엇이 어디에 쓰이는지 따로 이름 붙여 설명할 것이 없습니다.
            지우기는 격자 밖에 둡니다. 라벨 안의 버튼을 누르면 색 고르기 창까지 함께 열립니다. */}
        <p className={styles.colorNote}>
          <span>
            일정 목록에서 <OwnerName name={member.display_name} color={nextColor} /> 처럼 보입니다.
          </span>
          {/* 정해 둔 색이 있을 때만 나옵니다. 늘 흐릿하게 꺼져 있는 버튼은 자리만 차지합니다. */}
          {color !== '' && (
            <button type="button" className={styles.clear} onClick={() => setColor('')}>
              기본 회색으로 되돌리기
            </button>
          )}
        </p>

        {isSelf && (
          <p className={styles.hint}>
            자기 역할과 계정 상태는 바꿀 수 없습니다. 팀에 팀장이 없어지면 이 화면에 다시 들어올 수
            없습니다.
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

      {/* 담당 데이터 이관. 비활성을 고른 때만 나옵니다.
          목록 조회가 담당자의 재직 여부를 보기 때문에, 비활성으로 내리면 이 사람의
          거래처·딜·일정·고객불만이 팀장 화면에서도 보이지 않게 됩니다. 넘길 곳을 같은
          화면에서 고르지 못하면 그 사실을 알고도 할 수 있는 일이 없습니다.
          재직 중인 팀원에게는 숨깁니다 — 평소에 쓸 일이 없는 칸이고, 실수로 누르면
          남의 담당을 통째로 가져가는 일이 됩니다. */}
      {!isSelf && !active && counts !== null && (
        <section className={styles.section}>
          <h3 className={styles.heading}>담당 데이터 이관</h3>

          {total === 0 ? (
            <p className={styles.hint}>넘길 담당 데이터가 없습니다.</p>
          ) : (
            <>
              <dl className={styles.facts}>
                {(Object.keys(HANDOVER_LABEL) as (keyof HandoverCounts)[]).map((key) => (
                  <div key={key}>
                    <dt>{HANDOVER_LABEL[key]}</dt>
                    <dd className="tnum">{counts[key]}건</dd>
                  </div>
                ))}
              </dl>

              <p className={styles.warning} role="alert">
                {member.active
                  ? `비활성으로 저장하면 이 ${total}건이 팀장 화면을 포함한 모든 목록에서 보이지 않습니다. 먼저 이관해 주세요.`
                  : `이 ${total}건은 지금 팀장 화면을 포함한 모든 목록에서 보이지 않습니다. 이관하거나 다시 재직으로 되돌려 주세요.`}
              </p>

              <div className={styles.fields}>
                <FormField label="넘겨받을 팀원" htmlFor={false}>
                  <Select
                    label="넘겨받을 팀원"
                    value={heir}
                    options={heirOptions}
                    disabled={moving}
                    onChange={setHeir}
                  />
                </FormField>
              </div>
              <p className={styles.colorNote}>
                <span>거래처·딜·일정·고객불만의 담당자를 한 번에 바꿉니다.</span>
                <Button
                  variant="outline"
                  disabled={heir === '' || moving}
                  onClick={() => void moveWork()}
                >
                  {moving ? '이관 중…' : '이관하기'}
                </Button>
              </p>
              <p className={styles.hint}>
                등록자·작성자 기록은 그대로 둡니다. 목표 매출도 옮기지 않습니다.
              </p>
            </>
          )}
        </section>
      )}

      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </Drawer>
  )
}
