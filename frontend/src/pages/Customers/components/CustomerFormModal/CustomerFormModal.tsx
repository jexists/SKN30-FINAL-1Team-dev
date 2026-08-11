import { useState } from 'react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import {
  CUSTOMER_OWNERS,
  CUSTOMER_SOURCES,
  CUSTOMER_STATUSES,
  toCustomer,
} from '@/content/customers'
import type { Customer, CustomerSource, CustomerStatus } from '@/content/types'

import styles from './CustomerFormModal.module.scss'

interface CustomerFormModalProps {
  onClose: () => void
  onSubmit: (customer: Customer) => void
}

const EMPTY = {
  name: '',
  org: '',
  dept: '',
  title: '',
  email: '',
  phone: '',
  owner: CUSTOMER_OWNERS[0],
  source: CUSTOMER_SOURCES[0],
  status: CUSTOMER_STATUSES[0],
  memo: '',
}

type Draft = typeof EMPTY
type Errors = Partial<Record<keyof Draft, string>>

function validate(draft: Draft): Errors {
  const errors: Errors = {}
  if (draft.name.trim() === '') errors.name = '이름을 입력하세요.'
  if (draft.org.trim() === '') errors.org = '소속 회사를 입력하세요.'
  if (draft.email.trim() === '') errors.email = '이메일을 입력하세요.'
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(draft.email.trim()))
    errors.email = '이메일 형식이 맞지 않습니다. 예: name@hospital.kr'
  return errors
}

export default function CustomerFormModal({ onClose, onSubmit }: CustomerFormModalProps) {
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [errors, setErrors] = useState<Errors>({})

  const set = (key: keyof Draft, value: string) => setDraft((prev) => ({ ...prev, [key]: value }))

  const submit = () => {
    const found = validate(draft)
    setErrors(found)
    if (Object.keys(found).length > 0) return

    onSubmit(
      toCustomer({
        // 목업이라 서버가 번호를 주지 않습니다. 화면 안에서만 겹치지 않으면 됩니다.
        id: `FM-CU-NEW-${Date.now()}`,
        name: draft.name.trim(),
        org: draft.org.trim(),
        dept: draft.dept.trim(),
        title: draft.title.trim(),
        email: draft.email.trim(),
        phone: draft.phone.trim(),
        owner: draft.owner,
        source: draft.source as CustomerSource,
        status: draft.status as CustomerStatus,
        lastOff: 0,
        nextOff: null,
        createdOff: 0,
        memo: draft.memo.trim(),
      }),
    )
  }

  return (
    <Modal
      title="고객 등록"
      description="등록하면 목록 맨 위에 추가됩니다. 다음 일정은 캘린더에서 잡습니다."
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button type="submit">고객 등록</Button>
        </>
      }
    >
      <div className={styles.grid}>
        <Field label="이름" required error={errors.name}>
          <input value={draft.name} onChange={(e) => set('name', e.target.value)} />
        </Field>

        <Field label="회사" required error={errors.org}>
          <input
            value={draft.org}
            placeholder="한빛대학교병원"
            onChange={(e) => set('org', e.target.value)}
          />
        </Field>

        <Field label="부서">
          <input
            value={draft.dept}
            placeholder="순환기내과"
            onChange={(e) => set('dept', e.target.value)}
          />
        </Field>

        <Field label="직함">
          <input
            value={draft.title}
            placeholder="과장"
            onChange={(e) => set('title', e.target.value)}
          />
        </Field>

        <Field label="이메일" required error={errors.email} wide>
          <input
            type="email"
            value={draft.email}
            placeholder="name@hospital.kr"
            onChange={(e) => set('email', e.target.value)}
          />
        </Field>

        <Field label="전화">
          <input
            value={draft.phone}
            placeholder="02-000-0000"
            onChange={(e) => set('phone', e.target.value)}
          />
        </Field>

        <Field label="담당 영업">
          <select value={draft.owner} onChange={(e) => set('owner', e.target.value)}>
            {CUSTOMER_OWNERS.map((o) => (
              <option key={o}>{o}</option>
            ))}
          </select>
        </Field>

        <Field label="상태">
          <select value={draft.status} onChange={(e) => set('status', e.target.value)}>
            {CUSTOMER_STATUSES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </Field>

        <Field label="유입 소스">
          <select value={draft.source} onChange={(e) => set('source', e.target.value)}>
            {CUSTOMER_SOURCES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </Field>

        <Field label="메모" wide>
          <textarea
            rows={3}
            value={draft.memo}
            placeholder="다음에 확인할 것"
            onChange={(e) => set('memo', e.target.value)}
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
  children: React.ReactNode
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
