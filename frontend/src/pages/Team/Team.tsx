// 팀 관리. 구성원의 역할·재직 상태와 월 매출 목표를 다룹니다.
//
// 실적 조회는 이 화면이 아니라 Topbar 의 보기 범위 스위처가 맡습니다. 여기는
// "누가 팀에 있고 각자 얼마를 목표로 하는가"만 봅니다.
//
// 저장은 아직 화면 안에서만 일어납니다. 백엔드가 붙는 지점은 onSave 하나입니다.
import { useMemo, useState } from 'react'

import { useCurrentUser } from '@/auth/sessionContext'
import Button from '@/components/Button'
import { TEAM } from '@/shared/team'
import type { TeamMember } from '@/types'
import { wonFull } from '@/utils/format'

import MemberRow from './components/MemberRow'

import styles from './Team.module.scss'

export default function Team() {
  const { profile } = useCurrentUser()
  const [members, setMembers] = useState<TeamMember[]>(TEAM)
  // 저장하지 않은 편집분. 행 단위로 들고 있다가 저장할 때 명부에 반영합니다.
  const [drafts, setDrafts] = useState<Record<string, TeamMember>>({})

  const totalTarget = useMemo(
    () => members.reduce((sum, member) => sum + member.monthlyTarget, 0),
    [members],
  )

  const activeCount = members.filter((member) => member.active).length

  const editDraft = (id: string, patch: Partial<TeamMember>) => {
    setDrafts((prev) => {
      const base = prev[id] ?? members.find((member) => member.id === id)
      if (!base) return prev
      return { ...prev, [id]: { ...base, ...patch } }
    })
  }

  const save = (id: string) => {
    const draft = drafts[id]
    if (!draft) return
    setMembers((prev) => prev.map((member) => (member.id === id ? draft : member)))
    setDrafts((prev) => {
      const next = { ...prev }
      delete next[id]
      return next
    })
  }

  const cancel = (id: string) => {
    setDrafts((prev) => {
      const next = { ...prev }
      delete next[id]
      return next
    })
  }

  const dirtyCount = Object.keys(drafts).length

  return (
    <section className={styles.page}>
      {/* Topbar 빵부스러기가 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
      <h1 className="sr-only">팀 관리</h1>

      <div className={styles.summary}>
        <p className={styles.stat}>
          <span>재직 중인 구성원</span>
          <strong className="tnum">{activeCount}명</strong>
        </p>
        <p className={styles.stat}>
          <span>월 매출 목표 합계</span>
          <strong className="tnum">{wonFull(totalTarget)}</strong>
        </p>
        {dirtyCount > 0 && (
          <p className={styles.dirty} role="status">
            저장하지 않은 변경 {dirtyCount}건
          </p>
        )}
      </div>

      <div className={styles.card}>
        <div className={styles.scroller}>
          <table className={styles.table}>
            <caption className="sr-only">
              팀 구성원 목록. 역할·재직 상태·월 매출 목표를 바꿀 수 있습니다.
            </caption>
            <thead>
              <tr>
                <th scope="col">이름</th>
                <th scope="col">직함</th>
                <th scope="col">역할</th>
                <th scope="col">재직 상태</th>
                <th scope="col" className={styles.right}>
                  월 매출 목표
                </th>
                <th scope="col">
                  <span className="sr-only">저장</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {members.map((member) => (
                <MemberRow
                  key={member.id}
                  member={drafts[member.id] ?? member}
                  isSelf={member.name === profile.name}
                  dirty={drafts[member.id] !== undefined}
                  onEdit={(patch) => editDraft(member.id, patch)}
                  onSave={() => save(member.id)}
                  onCancel={() => cancel(member.id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <p className={styles.note}>
        변경은 아직 이 화면 안에만 남습니다. 새로고침하면 처음 값으로 돌아옵니다.
      </p>

      <div className={styles.foot}>
        <Button variant="outline" disabled={dirtyCount === 0} onClick={() => setDrafts({})}>
          변경 모두 취소
        </Button>
      </div>
    </section>
  )
}
