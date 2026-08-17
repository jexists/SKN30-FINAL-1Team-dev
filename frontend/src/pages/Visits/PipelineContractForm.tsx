import { useRef, useState, type ReactNode } from 'react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import type { ContractKind } from '@/types'
import { TODAY_ISO } from '@/utils/date'

import type {
  PipelineContract,
  PipelineContractSaveInput,
  PipelineOption,
} from './usePipelineContracts'

import styles from './PipelineContractForm.module.scss'

const KINDS: ContractKind[] = ['신규 도입', '증설', '갱신', '유지보수', '소모품 공급']

interface Props {
  contract?: PipelineContract
  stageName?: string
  companies: PipelineOption[]
  products: PipelineOption[]
  optionsLoading?: boolean
  onSubmit: (input: PipelineContractSaveInput) => Promise<void>
  onClose: () => void
}

interface FormState {
  customerCompanyId: string
  productId: string
  amount: string
  kind: ContractKind
  date: string
  memo: string
}

type Errors = Partial<Record<keyof FormState, string>>

export default function PipelineContractForm({
  contract,
  stageName,
  companies,
  products,
  optionsLoading = false,
  onSubmit,
  onClose,
}: Props) {
  const [form, setForm] = useState<FormState>(() => ({
    customerCompanyId: contract?.customerCompanyId ?? '',
    productId: contract?.productId ?? '',
    amount: contract ? String(contract.amount) : '',
    kind: contract?.kind ?? '신규 도입',
    date: contract?.date ?? TODAY_ISO,
    memo: contract?.memo ?? '',
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
    if (!companies.some(({ id }) => id === form.customerCompanyId)) {
      found.customerCompanyId = '고객사를 선택해 주세요.'
    }
    if (!products.some(({ id }) => id === form.productId)) {
      found.productId = '제품을 선택해 주세요.'
    }

    const amount = Number(form.amount)
    if (!/^\d+$/.test(form.amount) || !Number.isSafeInteger(amount)) {
      found.amount = '0 이상의 정수로 입력해 주세요.'
    }
    if (!form.date) found.date = '계약일을 선택해 주세요.'
    if (form.memo.length > 5000) found.memo = '메모는 5,000자까지 입력할 수 있습니다.'

    setErrors(found)
    if (Object.keys(found).length > 0) return

    submittingRef.current = true
    setSubmitting(true)
    setSubmitError(null)
    try {
      await onSubmit({
        customerCompanyId: form.customerCompanyId,
        productId: form.productId,
        amount,
        kind: form.kind,
        date: form.date,
        memo: form.memo.trim() || null,
      })
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '계약을 저장하지 못했습니다.')
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  const editing = contract !== undefined
  const noCompanies = !optionsLoading && companies.length === 0
  const noProducts = !optionsLoading && products.length === 0

  return (
    <Modal
      title={editing ? '영업 건 수정' : '영업 건 추가'}
      description={
        editing
          ? `${contract.no} · 단계는 보드에서 카드를 옮겨 바꿉니다.`
          : `${stageName ?? '선택한'} 단계에 추가됩니다. 계약번호는 자동으로 생성됩니다.`
      }
      onClose={close}
      onSubmit={() => void submit()}
      footer={
        <>
          <Button type="button" variant="outline" disabled={submitting} onClick={close}>
            취소
          </Button>
          <Button
            type="submit"
            disabled={submitting || optionsLoading || noCompanies || noProducts}
          >
            {submitting ? '저장 중…' : editing ? '저장' : '영업 건 추가'}
          </Button>
        </>
      }
    >
      <div className={styles.grid}>
        <Field label="고객사" required error={errors.customerCompanyId}>
          <select
            value={form.customerCompanyId}
            disabled={submitting || optionsLoading || noCompanies}
            onChange={(event) => set('customerCompanyId', event.target.value)}
          >
            <option value="">
              {optionsLoading
                ? '고객사를 불러오는 중…'
                : noCompanies
                  ? '등록된 고객사가 없습니다'
                  : '고객사를 선택하세요'}
            </option>
            {companies.map((company) => (
              <option key={company.id} value={company.id}>
                {company.name}
              </option>
            ))}
          </select>
        </Field>

        <Field label="제품" required error={errors.productId}>
          <select
            value={form.productId}
            disabled={submitting || optionsLoading || noProducts}
            onChange={(event) => set('productId', event.target.value)}
          >
            <option value="">
              {optionsLoading
                ? '제품을 불러오는 중…'
                : noProducts
                  ? '등록된 제품이 없습니다'
                  : '제품을 선택하세요'}
            </option>
            {products.map((product) => (
              <option key={product.id} value={product.id}>
                {product.name}
              </option>
            ))}
          </select>
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

        <Field label="유형" required>
          <select
            value={form.kind}
            disabled={submitting}
            onChange={(event) => set('kind', event.target.value as ContractKind)}
          >
            {KINDS.map((kind) => (
              <option key={kind}>{kind}</option>
            ))}
          </select>
        </Field>

        <Field label="계약일" required error={errors.date}>
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

      {(noCompanies || noProducts) && (
        <p className={styles.notice} role="status">
          {noCompanies && noProducts
            ? `영업 건을 ${editing ? '수정' : '추가'}하려면 고객사와 제품을 먼저 등록해 주세요.`
            : noCompanies
              ? `영업 건을 ${editing ? '수정' : '추가'}하려면 고객사를 먼저 등록해 주세요.`
              : `영업 건을 ${editing ? '수정' : '추가'}하려면 제품을 먼저 등록해 주세요.`}
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
