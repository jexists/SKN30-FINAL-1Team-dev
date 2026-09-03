import { useEffect, useRef, useState, type ReactNode } from 'react'

import { client } from '@/api/client'
import Button from '@/components/Button'
import CompanyAutocomplete, { type CompanySelection } from '@/components/CompanyAutocomplete'
import Modal from '@/components/Modal'
import RecordPicker, { type RecordOption } from '@/components/RecordPicker'
import type {
  CustomerCompanyCreateRequest,
  CustomerCompanyResponse,
  CustomerSourceCode,
  ProductResponse,
  SalesDealTypeResponse,
} from '@/types'
import { addDays, iso, TODAY } from '@/utils/date'

import type { SalesDeal, SalesDealColumn, SalesDealSaveInput } from './useSalesDeals'

import styles from './SalesDealForm.module.scss'

interface Props {
  deal?: SalesDeal
  columns: SalesDealColumn[]
  /** 추가할 단계. 보드에서 + 를 누른 칸이며, 수정은 딜이 서 있는 단계입니다. */
  stageId?: string
  onSubmit: (input: SalesDealSaveInput) => Promise<void>
  onClose: () => void
}

interface FormState {
  company: CompanySelection | null
  product: RecordOption | null
  title: string
  stageId: string
}

/**
 * 새 딜의 영업 시작일 기본값. 딜을 넣는 날은 대개 다음 만남을 잡는 날이라
 * 오늘이 아니라 내일에서 시작합니다.
 */
const DEFAULT_OPENED_ON = iso(addDays(TODAY, 1))

type Errors = Partial<Record<keyof FormState, string>>

/** 고른 회사의 id. 새로 등록하기로 한 회사는 이 시점에 만듭니다. */
async function resolveCompanyId(company: CompanySelection): Promise<string> {
  if (company.kind === 'existing') return company.company.id

  // 이 화면은 회사 이름만 묻습니다. 사업자번호와 주소는 고객 등록에서 채웁니다.
  const payload: CustomerCompanyCreateRequest = {
    name: company.name,
    region_code: null,
    business_no: null,
    postcode: null,
    address: null,
    address_detail: null,
  }
  // 그 사이 남이 같은 이름을 만들었으면 백엔드가 기존 행을 돌려줍니다.
  const { data } = await client.post<CustomerCompanyResponse>('/customer-companies', payload)
  return data.id
}

export default function SalesDealForm({ deal, columns, stageId, onSubmit, onClose }: Props) {
  const [form, setForm] = useState<FormState>(() => ({
    // 딜은 회사 id 와 이름만 들고 있습니다. 아래에서 한 건을 읽어 채웁니다.
    company: null,
    product: deal?.productId ? { id: deal.productId, label: deal.product } : null,
    title: deal?.title ?? '',
    stageId: stageId ?? columns[0]?.id ?? '',
  }))
  // 딜 유형은 이 모달의 저장에만 쓰입니다. 목록·보드는 쓰지 않아 여기서 받습니다.
  const [dealTypes, setDealTypes] = useState<SalesDealTypeResponse[]>([])
  const [optionsLoading, setOptionsLoading] = useState(true)
  const [errors, setErrors] = useState<Errors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const submittingRef = useRef(false)

  useEffect(() => {
    let live = true
    void client
      .get<SalesDealTypeResponse[]>('/sales-deal-types')
      .then(({ data }) => {
        if (live) setDealTypes(data)
      })
      .catch(() => {})
      .finally(() => {
        if (live) setOptionsLoading(false)
      })
    return () => {
      live = false
    }
  }, [])

  // 수정 화면의 고객사 칸이 빈칸으로 보이지 않게 지금 회사를 읽어 넣습니다.
  // 못 읽으면 비어 있는 채로 두고, 사람이 다시 고르면 됩니다.
  useEffect(() => {
    if (deal === undefined) return
    let live = true
    void client
      .get<CustomerCompanyResponse>(`/customer-companies/${deal.customerCompanyId}`)
      .then(({ data }) => {
        if (!live) return
        setForm((current) =>
          current.company === null
            ? { ...current, company: { kind: 'existing', company: data } }
            : current,
        )
      })
      .catch(() => {})
    return () => {
      live = false
    }
  }, [deal])

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
    if (form.stageId === '') found.stageId = '파이프라인 단계를 선택해 주세요.'
    if (form.title.length > 254) found.title = '제목은 254자까지 입력할 수 있습니다.'

    setErrors(found)
    if (form.company === null || form.product === null || Object.keys(found).length > 0) return

    submittingRef.current = true
    setSubmitting(true)
    setSubmitError(null)
    try {
      // 화면에서 묻지 않는 값입니다. 추가는 기본값으로, 수정은 원래 값 그대로 보냅니다.
      await onSubmit({
        customerCompanyId: await resolveCompanyId(form.company),
        productId: form.product.id,
        title: form.title.trim() || null,
        amount: deal?.amount ?? 0,
        dealTypeCode: deal?.dealTypeCode ?? dealTypes[0]?.code ?? '',
        date: deal?.date ?? DEFAULT_OPENED_ON,
        memo: deal?.memo ?? null,
        sourceCode: (deal?.sourceCode as CustomerSourceCode | null | undefined) ?? null,
        stageId: form.stageId,
        participantContactIds: (deal?.participants ?? []).map(
          (participant) => participant.customer_contact_id,
        ),
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
      description={editing ? `${deal.no} · 단계는 보드에서 카드를 옮겨 바꿉니다.` : undefined}
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
        <Field label="제목" error={errors.title} wide>
          <input
            value={form.title}
            disabled={submitting}
            maxLength={254}
            placeholder="비우면 '고객사 제품' 으로 채웁니다"
            onChange={(event) => set('title', event.target.value)}
          />
        </Field>

        <Field label="고객사" required error={errors.company}>
          <CompanyAutocomplete
            allowCreate
            label="고객사"
            placeholder="회사 이름으로 검색"
            disabled={submitting}
            invalid={errors.company !== undefined}
            value={form.company}
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

        <Field label="파이프라인" required error={errors.stageId}>
          <select
            value={form.stageId}
            // 수정에서 단계를 바꾸는 것은 카드 이동입니다. 여기서는 보여 주기만 합니다.
            disabled={submitting || editing || optionsLoading}
            onChange={(event) => set('stageId', event.target.value)}
          >
            {columns.map((column) => (
              <option key={column.id} value={column.id}>
                {column.name}
              </option>
            ))}
          </select>
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
