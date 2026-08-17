import { useState } from 'react'
import { isAxiosError } from 'axios'

import { client } from '@/api/client'
import Button from '@/components/Button'
import Modal from '@/components/Modal'
import type {
  CustomerCompanyResponse,
  CustomerContactCreateRequest,
  CustomerContactResponse,
  PageResponse,
} from '@/types'

import styles from './CustomerFormModal.module.scss'

interface CustomerFormModalProps {
  onClose: () => void
  onCreated: () => void
}

const EMPTY = {
  org: '',
  name: '',
  dept: '',
  title: '',
  email: '',
  phone: '',
  memo: '',
}

type Draft = typeof EMPTY
type Errors = Partial<Record<keyof Draft, string>>

function validate(draft: Draft): Errors {
  const errors: Errors = {}
  if (draft.org.trim() === '') errors.org = '소속 회사를 입력하세요.'
  if (draft.name.trim() === '') errors.name = '이름을 입력하세요.'
  if (draft.phone.trim() === '') errors.phone = '전화번호를 입력하세요.'
  if (draft.email.trim() !== '' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(draft.email.trim())) {
    errors.email = '이메일 형식이 맞지 않습니다. 예: name@company.com'
  }
  return errors
}

const optional = (value: string): string | null => value.trim() || null

async function findCompanies(name: string): Promise<CustomerCompanyResponse[]> {
  const { data } = await client.get<PageResponse<CustomerCompanyResponse>>('/customer-companies', {
    params: { q: name.slice(0, 100), skip: 0, limit: 100 },
  })
  return data.items
}

function submitErrorMessage(error: unknown): string {
  if (!isAxiosError(error)) return '고객을 등록하지 못했습니다.'
  if (error.response?.status === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.'
  if (error.response?.status === 404) return '고객사를 찾지 못했습니다. 다시 시도해 주세요.'
  if (error.response?.status === 422) return '입력한 내용을 확인해 주세요.'
  return '서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.'
}

export default function CustomerFormModal({ onClose, onCreated }: CustomerFormModalProps) {
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [errors, setErrors] = useState<Errors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const set = (key: keyof Draft, value: string) => {
    setDraft((previous) => ({ ...previous, [key]: value }))
    setErrors((previous) => ({ ...previous, [key]: undefined }))
    setSubmitError(null)
  }

  const submit = async () => {
    if (submitting) return

    const found = validate(draft)
    setErrors(found)
    if (Object.keys(found).length > 0) return

    setSubmitting(true)
    setSubmitError(null)

    try {
      const companyName = draft.org.trim()
      const companies = await findCompanies(companyName)
      const exact = companies.filter((company) => company.name === companyName)

      if (exact.length > 1) {
        setSubmitError('같은 이름의 고객사가 여러 개입니다. 고객사 정리 후 다시 등록해 주세요.')
        setSubmitting(false)
        return
      }

      let companyId = exact[0]?.id
      if (companyId === undefined) {
        const { data: createdCompany } = await client.post<CustomerCompanyResponse>(
          '/customer-companies',
          { name: companyName, region_code: null },
        )
        companyId = createdCompany.id
      }

      const payload: CustomerContactCreateRequest = {
        company_id: companyId,
        name: draft.name.trim(),
        department: optional(draft.dept),
        job_title: optional(draft.title),
        email: optional(draft.email),
        phone: draft.phone.trim(),
        status_code: 'new',
        source_code: null,
        memo: optional(draft.memo),
      }
      await client.post<CustomerContactResponse>('/customer-contacts', payload)
      setSubmitting(false)
      onCreated()
    } catch (error: unknown) {
      setSubmitError(submitErrorMessage(error))
      setSubmitting(false)
    }
  }

  const close = () => {
    if (!submitting) onClose()
  }

  return (
    <Modal
      title="고객 등록"
      onClose={close}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" disabled={submitting} onClick={close}>
            취소
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? '등록 중…' : '고객 등록'}
          </Button>
        </>
      }
    >
      <div className={styles.grid} aria-busy={submitting}>
        <Field label="회사" required error={errors.org}>
          <input
            value={draft.org}
            placeholder="회사 이름"
            maxLength={254}
            disabled={submitting}
            onChange={(event) => set('org', event.target.value)}
          />
        </Field>

        <Field label="이름" required error={errors.name}>
          <input
            value={draft.name}
            maxLength={254}
            disabled={submitting}
            onChange={(event) => set('name', event.target.value)}
          />
        </Field>

        <Field label="부서">
          <input
            value={draft.dept}
            placeholder="부서 이름"
            maxLength={254}
            disabled={submitting}
            onChange={(event) => set('dept', event.target.value)}
          />
        </Field>

        <Field label="직함">
          <input
            value={draft.title}
            placeholder="과장"
            maxLength={254}
            disabled={submitting}
            onChange={(event) => set('title', event.target.value)}
          />
        </Field>

        <Field label="이메일" error={errors.email}>
          <input
            type="email"
            value={draft.email}
            placeholder="name@company.com"
            maxLength={254}
            disabled={submitting}
            onChange={(event) => set('email', event.target.value)}
          />
        </Field>

        <Field label="전화" required error={errors.phone}>
          <input
            type="tel"
            value={draft.phone}
            placeholder="02-000-0000"
            maxLength={50}
            disabled={submitting}
            onChange={(event) => set('phone', event.target.value)}
          />
        </Field>

        <Field label="메모" wide>
          <textarea
            rows={3}
            value={draft.memo}
            placeholder="참고사항"
            maxLength={5000}
            disabled={submitting}
            onChange={(event) => set('memo', event.target.value)}
          />
        </Field>
      </div>

      {submitError && (
        <p className={styles.error} role="alert">
          {submitError}
        </p>
      )}
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
