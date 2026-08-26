import { useRef, useState, type ReactNode } from 'react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import RecordPicker, { type RecordOption } from '@/components/RecordPicker'
import type { CustomerCompanyResponse, ProductResponse, SalesDealTypeResponse } from '@/types'
import { formatBusinessNo } from '@/utils/format'
import { TODAY_ISO } from '@/utils/date'

import type { SalesDeal, SalesDealSaveInput } from './useSalesDeals'

import styles from './SalesDealForm.module.scss'

interface Props {
  deal?: SalesDeal
  stageName?: string
  dealTypes: SalesDealTypeResponse[]
  optionsLoading?: boolean
  onSubmit: (input: SalesDealSaveInput) => Promise<void>
  onClose: () => void
}

interface FormState {
  company: RecordOption | null
  product: RecordOption | null
  amount: string
  dealTypeCode: string
  date: string
  memo: string
}

type Errors = Partial<Record<keyof FormState, string>>

export default function SalesDealForm({
  deal,
  stageName,
  dealTypes,
  optionsLoading = false,
  onSubmit,
  onClose,
}: Props) {
  const [form, setForm] = useState<FormState>(() => ({
    // 수정 화면은 이미 이름을 들고 있어 한 건을 다시 물어볼 필요가 없습니다.
    company: deal ? { id: deal.customerCompanyId, label: deal.org } : null,
    product: deal?.productId ? { id: deal.productId, label: deal.product } : null,
    amount: deal ? String(deal.amount) : '',
    dealTypeCode: deal?.dealTypeCode ?? dealTypes[0]?.code ?? '',
    date: deal?.date ?? TODAY_ISO,
    memo: deal?.memo ?? '',
  }))
  const [errors, setErrors] = useState<Errors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const submittingRef = useRef(false)

  const set = <Key extends keyof FormState>(key: Key, value: FormState[Key]) => {
    setForm((current) => ({ ...current, [key]: value }))
    setErrors((current) => ({ ...current, [key]: undefined }))
  }

  const close = () => {
    if (!submittingRef.current) onClose()
  }

  const submit = async () => {
    if (submittingRef.current) return

    const found: Errors = {}
    if (form.company === null) found.company = '고객사를 선택해 주세요.'
    if (form.product === null) found.product = '제품을 선택해 주세요.'
    if (
      !dealTypes.some(({ code }) => code === form.dealTypeCode) &&
      form.dealTypeCode !== deal?.dealTypeCode
    ) {
      found.dealTypeCode = '영업 유형을 선택해 주세요.'
    }

    const amount = Number(form.amount)
    if (!/^\d+$/.test(form.amount) || !Number.isSafeInteger(amount)) {
      found.amount = '0 이상의 정수로 입력해 주세요.'
    }
    if (!form.date) found.date = '영업 시작일을 선택해 주세요.'
    if (form.memo.length > 5000) found.memo = '메모는 5,000자까지 입력할 수 있습니다.'

    setErrors(found)
    if (form.company === null || form.product === null || Object.keys(found).length > 0) return

    submittingRef.current = true
    setSubmitting(true)
    setSubmitError(null)
    try {
      await onSubmit({
        customerCompanyId: form.company.id,
        productId: form.product.id,
        amount,
        dealTypeCode: form.dealTypeCode,
        date: form.date,
        memo: form.memo.trim() || null,
      })
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '영업 딜을 저장하지 못했습니다.')
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  const editing = deal !== undefined
  const noDealTypes = !optionsLoading && dealTypes.length === 0 && !deal?.dealTypeCode

  return (
    <Modal
      title={editing ? '영업 딜 수정' : '영업 딜 추가'}
      description={
        editing
          ? `${deal.no} · 단계는 보드에서 카드를 옮겨 바꿉니다.`
          : `${stageName ?? '선택한'} 단계에 추가됩니다. 영업번호는 자동으로 생성됩니다.`
      }
      onClose={close}
      onSubmit={() => void submit()}
      footer={
        <>
          <Button type="button" variant="outline" disabled={submitting} onClick={close}>
            취소
          </Button>
          <Button type="submit" disabled={submitting || optionsLoading || noDealTypes}>
            {submitting ? '저장 중…' : editing ? '저장' : '영업 딜 추가'}
          </Button>
        </>
      }
    >
      <div className={styles.grid}>
        <Field label="고객사" required error={errors.company}>
          <RecordPicker<CustomerCompanyResponse>
            path="/customer-companies"
            label="고객사"
            placeholder="회사 이름으로 검색"
            emptyText="일치하는 고객사가 없습니다."
            loadingText="고객사를 불러오는 중입니다."
            fallback="고객사를 불러오지 못했습니다."
            value={form.company}
            disabled={submitting}
            invalid={errors.company !== undefined}
            toOption={(row) => ({
              id: row.id,
              label: row.name,
              note: formatBusinessNo(row.business_no) ?? undefined,
            })}
            onChange={(next) => set('company', next)}
          />
        </Field>

        <Field label="제품" required error={errors.product}>
          <RecordPicker<ProductResponse>
            path="/products"
            label="제품"
            placeholder="제품 이름으로 검색"
            emptyText="일치하는 제품이 없습니다."
            loadingText="제품을 불러오는 중입니다."
            fallback="제품을 불러오지 못했습니다."
            value={form.product}
            disabled={submitting}
            invalid={errors.product !== undefined}
            toOption={(row) => ({ id: row.id, label: row.name })}
            onChange={(next) => set('product', next)}
          />
        </Field>

        <Field label="금액 (원)" required error={errors.amount}>
          <input
            type="number"
            min="0"
            step="1"
            value={form.amount}
            disabled={submitting}
            placeholder="28400000"
            onChange={(event) => set('amount', event.target.value)}
          />
        </Field>

        <Field label="유형" required error={errors.dealTypeCode}>
          <select
            value={form.dealTypeCode}
            disabled={submitting || optionsLoading || noDealTypes}
            onChange={(event) => set('dealTypeCode', event.target.value)}
          >
            {deal && !dealTypes.some(({ code }) => code === deal.dealTypeCode) && (
              <option value={deal.dealTypeCode}>{deal.kind} (기존값)</option>
            )}
            {dealTypes.map((dealType) => (
              <option key={dealType.id} value={dealType.code}>
                {dealType.name}
              </option>
            ))}
          </select>
        </Field>

        <Field label="영업 시작일" required error={errors.date}>
          <input
            type="date"
            value={form.date}
            disabled={submitting}
            onChange={(event) => set('date', event.target.value)}
          />
        </Field>

        <Field label="메모" error={errors.memo} wide>
          <textarea
            rows={4}
            maxLength={5000}
            value={form.memo}
            disabled={submitting}
            placeholder="다음에 확인할 것"
            onChange={(event) => set('memo', event.target.value)}
          />
        </Field>
      </div>

      {noDealTypes && (
        <p className={styles.notice} role="status">
          {`영업 딜을 ${editing ? '수정' : '추가'}하려면 영업 유형이 하나 이상 필요합니다.`}
        </p>
      )}
      {submitError && (
        <p className={styles.submitError} role="alert">
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
  children: ReactNode
}

function Field({ label, required, error, wide, children }: FieldProps) {
  return (
    <label className={[styles.field, wide ? styles.wide : ''].filter(Boolean).join(' ')}>
      <span className={styles.label}>
        {label}
        {required && <b aria-hidden="true">*</b>}
      </span>
      {children}
      {error && <span className={styles.error}>{error}</span>}
    </label>
  )
}
