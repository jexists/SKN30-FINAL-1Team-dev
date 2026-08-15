// 불만 등록. 받는 값은 다섯 개뿐입니다 — 제목·회사·담당자·내용·상태.
// 접수자·제품처럼 시드에만 있는 칸은 비워 두고, 목록과 드로어가 그 칸을 그리지 않습니다.
import { useState, type ReactNode } from 'react'

import { useCurrentUser } from '@/auth/sessionContext'
import Button from '@/components/Button'
import Modal from '@/components/Modal'
import type { CsDraft } from '@/shared/counters'
import type { CsState } from '@/types'

import styles from '../Complaints.module.scss'

const STATES: CsState[] = ['처리중', '처리완료']

interface Props {
  onClose: () => void
  onSubmit: (draft: CsDraft) => void
}

type Errors = Partial<Record<'issue' | 'org' | 'owner', string>>

export default function ComplaintFormModal({ onClose, onSubmit }: Props) {
  const { profile } = useCurrentUser()

  const [issue, setIssue] = useState('')
  const [org, setOrg] = useState('')
  // 담당 영업은 보통 접수한 본인입니다. 비어 있으면 목록에서 담당자 칸이 빕니다.
  const [owner, setOwner] = useState(profile.name)
  const [product, setProduct] = useState('')
  const [note, setNote] = useState('')
  const [state, setState] = useState<CsState>('처리중')
  const [urgent, setUrgent] = useState(false)
  const [errors, setErrors] = useState<Errors>({})

  const submit = () => {
    const found: Errors = {}
    if (issue.trim() === '') found.issue = '제목을 입력하세요.'
    if (org.trim() === '') found.org = '회사를 입력하세요.'
    if (owner.trim() === '') found.owner = '담당자를 입력하세요.'
    setErrors(found)
    if (Object.keys(found).length > 0) return

    onSubmit({
      issue: issue.trim(),
      org: org.trim(),
      owner: owner.trim(),
      product: product.trim(),
      note: note.trim(),
      state,
      urgent,
    })
  }

  return (
    <Modal
      title="불만 등록"
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button type="submit">불만 등록</Button>
        </>
      }
    >
      {/* 칸 순서는 목록의 열 순서와 같습니다 — 회사·담당자·제목·물품명·상태·내용. */}
      <div className={styles.grid}>
        <Field label="회사" required error={errors.org}>
          <input value={org} placeholder="회사 이름" onChange={(e) => setOrg(e.target.value)} />
        </Field>

        <Field label="담당자" required error={errors.owner}>
          <input value={owner} onChange={(e) => setOwner(e.target.value)} />
        </Field>

        <Field label="제목" required error={errors.issue} wide>
          <input
            value={issue}
            placeholder="부팅 시 화면 깜빡임"
            onChange={(e) => setIssue(e.target.value)}
          />
        </Field>

        <Field label="물품명" wide>
          <input
            value={product}
            placeholder="CardioView X7"
            onChange={(e) => setProduct(e.target.value)}
          />
        </Field>

        <Field label="상태">
          <select value={state} onChange={(e) => setState(e.target.value as CsState)}>
            {STATES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </Field>

        {/* 대시보드 C/S 타일이 이 값을 '긴급 N건' 으로 셉니다.
            fieldset/legend 는 flex 안에서 브라우저마다 다르게 자리를 잡아 옆 칸과 높이가
            어긋납니다. 다른 칸과 같은 마크업을 쓰고 그룹 역할만 role 로 알립니다. */}
        <div className={styles.field}>
          <span className={styles.label}>긴급도</span>
          <div className={styles.tags} role="radiogroup" aria-label="긴급도">
            {/* 라디오 두 개를 태그 모양으로 입힙니다. 고른 것만 색이 차고,
                긴급은 목록에 붙을 배지와 같은 주황입니다. 기본은 보통입니다. */}
            <label className={styles.tag}>
              <input
                type="radio"
                name="urgent"
                checked={!urgent}
                onChange={() => setUrgent(false)}
              />
              <span>보통</span>
            </label>
            <label className={`${styles.tag} ${styles.urgentTag}`}>
              <input type="radio" name="urgent" checked={urgent} onChange={() => setUrgent(true)} />
              <span>긴급</span>
            </label>
          </div>
        </div>

        <Field label="내용" wide>
          <textarea
            rows={4}
            value={note}
            placeholder="접수한 내용과 처리 상황"
            onChange={(e) => setNote(e.target.value)}
          />
        </Field>
      </div>
    </Modal>
  )
}

interface FieldProps {
  label: string
  required?: boolean
  error?: string
  wide?: boolean
  children: ReactNode
}

function Field({ label, required, error, wide, children }: FieldProps) {
  return (
    <label className={`${styles.field} ${wide ? styles.isWide : ''}`}>
      <span className={styles.label}>
        {label}
        {required && <b aria-hidden="true">*</b>}
      </span>
      {children}
      {error && <span className={styles.error}>{error}</span>}
    </label>
  )
}
