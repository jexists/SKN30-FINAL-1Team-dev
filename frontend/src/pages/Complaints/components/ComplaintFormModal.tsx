import { useState, type ReactNode } from 'react'

import Button from '@/components/Button'
import CompanyAutocomplete, { type CompanySelection } from '@/components/CompanyAutocomplete'
import DateTimePicker from '@/components/DateTimePicker'
import Modal from '@/components/Modal'
import RecordPicker, { type RecordOption } from '@/components/RecordPicker'
import Select from '@/components/Select'
import type {
  SalesDealResponse,
  SupportRequestCreateRequest,
  SupportRequestPatchRequest,
  SupportRequestResponse,
  SupportStatusCode,
} from '@/types'

import { STATE_OPTIONS } from '../statuses'
import { mutationErrorMessage } from '../useSupportRequests'

import styles from '../Complaints.module.scss'

// 불만을 걸 수 있는 딜. 계약이 실제로 맺어진 뒤의 딜만 후보입니다.
// 서버의 support.py `_COMPLAINT_PHASES` 와 같아야 합니다.
const COMPLAINT_PHASES = ['contract', 'order', 'closed']

interface Props {
  /**
   * 있으면 수정 모드입니다. 회사·딜은 고칠 수 없어 읽기 전용 줄로만 서고, 상태도 빠집니다.
   * 상태는 드로어 아래 "상태 변경"이 낙관적 잠금까지 걸어 가며 따로 맡고 있습니다.
   */
  initial?: SupportRequestResponse
  onClose: () => void
  /** 등록 모드에서만 옵니다. */
  onSubmit?: (payload: SupportRequestCreateRequest) => Promise<void>
  /** 수정 모드에서만 옵니다. */
  onPatch?: (patch: SupportRequestPatchRequest) => Promise<void>
}

type Errors = Partial<Record<'company' | 'deal' | 'title' | 'body', string>>

export default function ComplaintFormModal({ initial, onClose, onSubmit, onPatch }: Props) {
  const editing = initial !== undefined

  const [company, setCompany] = useState<CompanySelection | null>(null)
  const [deal, setDeal] = useState<RecordOption | null>(null)
  // 고른 딜의 제품·워런티. RecordPicker 는 id 와 이름만 주므로 행을 따로 붙듭니다.
  const [dealRow, setDealRow] = useState<SalesDealResponse | null>(null)
  const [title, setTitle] = useState(initial?.title ?? '')
  const [body, setBody] = useState(initial?.body ?? '')
  const [statusCode, setStatusCode] = useState<SupportStatusCode>('received')
  const [urgent, setUrgent] = useState(initial?.is_urgent ?? false)
  const [occurredAt, setOccurredAt] = useState(() =>
    initial ? new Date(initial.occurred_at) : new Date(),
  )
  const [errors, setErrors] = useState<Errors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // allowCreate 를 껐으므로 고를 수 있는 값은 이미 등록된 고객사뿐입니다.
  const companyId = company?.kind === 'existing' ? company.company.id : ''

  const submit = async () => {
    if (submitting) return

    const found: Errors = {}
    if (!editing && companyId === '') found.company = '회사를 선택하세요.'
    if (!editing && deal === null) found.deal = '딜을 선택하세요.'
    if (title.trim() === '') found.title = '제목을 입력하세요.'
    if (body.trim() === '') found.body = '내용을 입력하세요.'
    setErrors(found)
    if (Object.keys(found).length > 0) return

    if (initial && onPatch) {
      const patch = changedFields(initial, {
        title: title.trim(),
        body: body.trim(),
        is_urgent: urgent,
        occurred_at: occurredAt.toISOString(),
      })
      // 고친 것이 없으면 서버까지 갈 일이 없습니다. 서버도 빈 본문은 422 로 돌려보냅니다.
      if (Object.keys(patch).length === 0) {
        onClose()
        return
      }

      setSubmitting(true)
      setSubmitError(null)
      try {
        await onPatch(patch)
      } catch (caught: unknown) {
        setSubmitError(mutationErrorMessage(caught, '고객불만을 수정'))
        setSubmitting(false)
      }
      return
    }

    if (companyId === '' || deal === null || !onSubmit) return

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
      title={editing ? '고객불만 수정' : '고객불만 등록'}
      onClose={close}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" disabled={submitting} onClick={close}>
            취소
          </Button>
          <Button type="submit" disabled={submitting}>
            {editing
              ? submitting
                ? '저장 중…'
                : '수정 저장'
              : submitting
                ? '등록 중…'
                : '불만 등록'}
          </Button>
        </>
      }
    >
      <div className={styles.grid} aria-busy={submitting}>
        {initial ? (
          <>
            <ReadOnlyField label="회사" value={initial.customer_company_name} />
            <ReadOnlyField
              label="딜선택"
              value={`${initial.contract_no ?? initial.deal_no} · ${initial.deal_title}`}
              hint={`제품 ${initial.product_name ?? '미지정'} · 워런티 ${initial.warranty_terms ?? '없음'}`}
            />
          </>
        ) : (
          <>
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
                placeholder={
                  companyId === '' ? '회사를 먼저 선택하세요' : '계약번호나 제목으로 검색'
                }
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
                  제품 {dealRow.product_name ?? '미지정'} · 워런티{' '}
                  {dealRow.warranty_terms ?? '없음'}
                </span>
              )}
            </Field>
          </>
        )}

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

        {!editing && (
          <Field label="상태" required htmlFor={false}>
            <Select
              label="상태"
              value={statusCode}
              options={STATE_OPTIONS}
              disabled={submitting}
              onChange={(next) => setStatusCode(next as SupportStatusCode)}
            />
          </Field>
        )}

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

/** 수정 모드에서 회사·딜 자리에 서는 읽기 전용 줄입니다. */
function ReadOnlyField({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className={`${styles.field} ${styles.isWide}`}>
      <span className={styles.label}>{label}</span>
      <p className={styles.readOnly}>{value}</p>
      {hint && <span className={styles.dealHint}>{hint}</span>}
    </div>
  )
}

/** 수정 폼이 실제로 바꾼 칸만 골라냅니다. */
function changedFields(
  initial: SupportRequestResponse,
  next: Required<SupportRequestPatchRequest>,
): SupportRequestPatchRequest {
  const patch: SupportRequestPatchRequest = {}
  if (next.title !== initial.title) patch.title = next.title
  if (next.body !== initial.body) patch.body = next.body
  if (next.is_urgent !== initial.is_urgent) patch.is_urgent = next.is_urgent
  // 발생일시는 문자열 표기가 달라도 같은 순간일 수 있습니다. 시각으로 견줍니다.
  if (new Date(next.occurred_at).getTime() !== new Date(initial.occurred_at).getTime()) {
    patch.occurred_at = next.occurred_at
  }
  return patch
}

interface FieldProps {
  label: string
  required?: boolean
  error?: string
  wide?: boolean
  /**
   * label 로 감쌀지 여부. Select 처럼 버튼으로 여는 칸은 라벨 글자를 눌러도 함께
   * 눌리거나 포커스가 엉킵니다. 그런 칸은 false 로 두고 div 로 감쌉니다.
   */
  htmlFor?: boolean
  children: ReactNode
}

function Field({ label, required, error, wide, htmlFor = true, children }: FieldProps) {
  const Wrapper = htmlFor ? 'label' : 'div'
  return (
    <Wrapper className={`${styles.field} ${wide ? styles.isWide : ''}`}>
      <span className={styles.label}>
        {label}
        {required && <b aria-hidden="true">*</b>}
      </span>
      {children}
      {error && <span className={styles.error}>{error}</span>}
    </Wrapper>
  )
}
