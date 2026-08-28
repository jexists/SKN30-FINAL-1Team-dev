import { useState, type ReactNode } from 'react'

import Button from '@/components/Button'
import CompanyAutocomplete, { type CompanySelection } from '@/components/CompanyAutocomplete'
import DateTimePicker from '@/components/DateTimePicker'
import Modal from '@/components/Modal'
import RecordPicker, { type RecordOption } from '@/components/RecordPicker'
import type { SalesDealResponse, SupportRequestCreateRequest, SupportStatusCode } from '@/types'

import { STATES } from '../statuses'
import { mutationErrorMessage } from '../useSupportRequests'

import styles from '../Complaints.module.scss'

// 불만을 걸 수 있는 딜. 계약이 실제로 맺어진 뒤의 딜만 후보입니다.
// 서버의 support.py `_COMPLAINT_PHASES` 와 같아야 합니다.
const COMPLAINT_PHASES = ['contract', 'order', 'closed']

interface Props {
  onClose: () => void
  onSubmit: (payload: SupportRequestCreateRequest) => Promise<void>
}

type Errors = Partial<Record<'company' | 'deal' | 'title' | 'body', string>>

export default function ComplaintFormModal({ onClose, onSubmit }: Props) {
  const [company, setCompany] = useState<CompanySelection | null>(null)
  const [deal, setDeal] = useState<RecordOption | null>(null)
  // 고른 딜의 제품·워런티. RecordPicker 는 id 와 이름만 주므로 행을 따로 붙듭니다.
  const [dealRow, setDealRow] = useState<SalesDealResponse | null>(null)
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [statusCode, setStatusCode] = useState<SupportStatusCode>('received')
  const [urgent, setUrgent] = useState(false)
  const [occurredAt, setOccurredAt] = useState(() => new Date())
  const [errors, setErrors] = useState<Errors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // allowCreate 를 껐으므로 고를 수 있는 값은 이미 등록된 고객사뿐입니다.
  const companyId = company?.kind === 'existing' ? company.company.id : ''

  const submit = async () => {
    if (submitting) return

    const found: Errors = {}
    if (companyId === '') found.company = '회사를 선택하세요.'
    if (deal === null) found.deal = '딜을 선택하세요.'
    if (title.trim() === '') found.title = '제목을 입력하세요.'
    if (body.trim() === '') found.body = '내용을 입력하세요.'
    setErrors(found)
    if (companyId === '' || deal === null || Object.keys(found).length > 0) return

    setSubmitting(true)
    setSubmitError(null)
    try {
      await onSubmit({
        customer_company_id: companyId,
        sales_deal_id: deal.id,
        title: title.trim(),
        body: body.trim(),
        is_urgent: urgent,
        status_code: statusCode,
        occurred_at: occurredAt.toISOString(),
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
      title="고객불만 등록"
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
        <Field label="회사" required error={errors.company} wide>
          <CompanyAutocomplete
            label="회사"
            placeholder="회사 이름으로 검색"
            value={company}
            disabled={submitting}
            invalid={errors.company !== undefined}
            onChange={(next) => {
              setCompany(next)
              // 회사가 바뀌면 고른 딜은 남의 회사 것이 됩니다. 함께 비웁니다.
              setDeal(null)
              setDealRow(null)
              setErrors((previous) => ({ ...previous, company: undefined }))
            }}
          />
        </Field>

        <Field label="딜선택" required error={errors.deal} wide>
          <RecordPicker<SalesDealResponse>
            path="/sales-deals"
            label="딜"
            placeholder={companyId === '' ? '회사를 먼저 선택하세요' : '계약번호나 제목으로 검색'}
            emptyText="일치하는 딜이 없습니다."
            loadingText="딜을 불러오는 중입니다."
            fallback="딜을 불러오지 못했습니다."
            // 회사와 단계는 서버가 거릅니다. 전건을 받아 화면에서 거르면 첫 쪽이
            // 30건으로 끊기지 않습니다.
            params={{ customer_company_id: companyId, phase_code: COMPLAINT_PHASES }}
            value={deal}
            disabled={submitting || companyId === ''}
            invalid={errors.deal !== undefined}
            toOption={(row) => ({
              id: row.id,
              label: row.contract_no ?? row.deal_no,
              note: row.title,
            })}
            onChange={(next, row) => {
              setDeal(next)
              setDealRow(row)
              setErrors((previous) => ({ ...previous, deal: undefined }))
            }}
          />
          {dealRow && (
            <span className={styles.dealHint}>
              제품 {dealRow.product_name ?? '미지정'} · 워런티 {dealRow.warranty_terms ?? '없음'}
            </span>
          )}
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

        <Field label="상태" required>
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

        <Field label="발생 날짜" required>
          <DateTimePicker
            label="발생 날짜"
            selected={occurredAt}
            onChange={(next) => {
              if (next) setOccurredAt(next)
            }}
          />
        </Field>

        <label className={`${styles.field} ${styles.urgentField}`}>
          <span className={styles.label}>긴급도</span>
          <span className={styles.check}>
            <input
              type="checkbox"
              checked={urgent}
              disabled={submitting}
              onChange={(event) => setUrgent(event.target.checked)}
            />
            <span>긴급</span>
          </span>
        </label>

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
