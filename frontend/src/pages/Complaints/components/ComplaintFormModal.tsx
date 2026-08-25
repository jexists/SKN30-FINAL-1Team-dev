import { useState, type ReactNode } from 'react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import RecordPicker, { type RecordOption } from '@/components/RecordPicker'
import type {
  CustomerContactResponse,
  SupportRequestCreateRequest,
  SupportStatusCode,
} from '@/types'

import { mutationErrorMessage } from '../useSupportRequests'

import styles from '../Complaints.module.scss'

const STATES: { code: SupportStatusCode; label: string }[] = [
  { code: 'in_progress', label: '처리중' },
  { code: 'completed', label: '처리완료' },
]

interface Props {
  onClose: () => void
  onSubmit: (payload: SupportRequestCreateRequest) => Promise<void>
}

type Errors = Partial<Record<'contact' | 'title' | 'body', string>>

export default function ComplaintFormModal({ onClose, onSubmit }: Props) {
  const [contact, setContact] = useState<RecordOption | null>(null)
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [statusCode, setStatusCode] = useState<SupportStatusCode>('in_progress')
  const [urgent, setUrgent] = useState(false)
  const [errors, setErrors] = useState<Errors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const submit = async () => {
    if (submitting) return

    const found: Errors = {}
    if (contact === null) found.contact = '고객 담당자를 선택하세요.'
    if (title.trim() === '') found.title = '제목을 입력하세요.'
    if (body.trim() === '') found.body = '내용을 입력하세요.'
    setErrors(found)
    if (contact === null || Object.keys(found).length > 0) return

    setSubmitting(true)
    setSubmitError(null)
    try {
      await onSubmit({
        customer_contact_id: contact.id,
        title: title.trim(),
        body: body.trim(),
        is_urgent: urgent,
        status_code: statusCode,
      })
    } catch (caught: unknown) {
      setSubmitError(mutationErrorMessage(caught, '고객불만을 등록'))
      setSubmitting(false)
    }
  }

  const close = () => {
    if (!submitting) onClose()
  }

  return (
    <Modal
      title="불만 등록"
      onClose={close}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" disabled={submitting} onClick={close}>
            취소
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? '등록 중…' : '불만 등록'}
          </Button>
        </>
      }
    >
      <div className={styles.grid} aria-busy={submitting}>
        <Field label="고객 담당자" required error={errors.contact} wide>
          <RecordPicker<CustomerContactResponse>
            path="/customer-contacts"
            label="고객 담당자"
            placeholder="회사나 담당자 이름으로 검색"
            emptyText="일치하는 고객 담당자가 없습니다."
            loadingText="고객 담당자를 불러오는 중입니다."
            fallback="고객 담당자를 불러오지 못했습니다."
            value={contact}
            disabled={submitting}
            invalid={errors.contact !== undefined}
            toOption={(row) => ({
              id: row.id,
              label: row.name,
              note: row.company_name,
            })}
            onChange={(next) => {
              setContact(next)
              setErrors((previous) => ({ ...previous, contact: undefined }))
            }}
          />
        </Field>

        <Field label="제목" required error={errors.title} wide>
          <input
            value={title}
            maxLength={254}
            disabled={submitting}
            placeholder="요청 내용을 요약해 주세요"
            onChange={(event) => {
              setTitle(event.target.value)
              setErrors((previous) => ({ ...previous, title: undefined }))
            }}
          />
        </Field>

        <Field label="상태">
          <select
            value={statusCode}
            disabled={submitting}
            onChange={(event) => setStatusCode(event.target.value as SupportStatusCode)}
          >
            {STATES.map((state) => (
              <option key={state.code} value={state.code}>
                {state.label}
              </option>
            ))}
          </select>
        </Field>

        <div className={styles.field}>
          <span className={styles.label}>긴급도</span>
          <div className={styles.tags} role="radiogroup" aria-label="긴급도">
            <label className={styles.tag}>
              <input
                type="radio"
                name="urgent"
                checked={!urgent}
                disabled={submitting}
                onChange={() => setUrgent(false)}
              />
              <span>보통</span>
            </label>
            <label className={`${styles.tag} ${styles.urgentTag}`}>
              <input
                type="radio"
                name="urgent"
                checked={urgent}
                disabled={submitting}
                onChange={() => setUrgent(true)}
              />
              <span>긴급</span>
            </label>
          </div>
        </div>

        <Field label="내용" required error={errors.body} wide>
          <textarea
            rows={5}
            value={body}
            maxLength={5_000}
            disabled={submitting}
            placeholder="접수한 내용을 입력해 주세요"
            onChange={(event) => {
              setBody(event.target.value)
              setErrors((previous) => ({ ...previous, body: undefined }))
            }}
          />
        </Field>

        {submitError && (
          <p className={`${styles.error} ${styles.isWide}`} role="alert">
            {submitError}
          </p>
        )}
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
