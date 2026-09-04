import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

import { client } from '@/api/client'
import Button from '@/components/Button'
import CompanyAutocomplete, { type CompanySelection } from '@/components/CompanyAutocomplete'
import ContactPicker, { toContactOption, type ContactOption } from '@/components/ContactPicker'
import Modal from '@/components/Modal'
import RecordPicker, { type RecordOption } from '@/components/RecordPicker'
import CustomerFormModal from '@/pages/Customers/components/CustomerFormModal'
import type {
  CustomerCompanyResponse,
  CustomerContactResponse,
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
  /**
   * 새 딜의 고객사·담당자를 부르는 쪽이 이미 정해 온 경우입니다. 일정 등록처럼 회사와
   * 사람이 먼저 정해진 자리에서 씁니다. 준 칸만 잠깁니다 — 여기서 다른 값을 고를 수
   * 있으면 부르는 쪽이 들고 있는 값과 어긋나기 때문입니다. 반대로 주지 않은 칸까지
   * 잠그면 채울 방법이 없는 필수 칸이 생깁니다.
   */
  initialCompany?: CustomerCompanyResponse
  initialContact?: ContactOption
  onSubmit: (input: SalesDealSaveInput) => Promise<void>
  onClose: () => void
}

interface FormState {
  company: CompanySelection | null
  /** 이 딜의 대표 담당자. 회사를 바꾸면 그 전 회사 사람이 남지 않게 함께 비웁니다. */
  contact: ContactOption | null
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

/**
 * 고른 회사의 id. 아직 없는 회사는 고객 등록으로 넘겨 회사와 담당자를 함께 만들므로
 * 이 칸에 남는 것은 늘 이미 있는 회사입니다.
 */
function companyId(company: CompanySelection | null): string | null {
  return company?.kind === 'existing' ? company.company.id : null
}

export default function SalesDealForm({
  deal,
  columns,
  stageId,
  initialCompany,
  initialContact,
  onSubmit,
  onClose,
}: Props) {
  // 부르는 쪽이 정해 온 칸만 잠급니다.
  const companyLocked = initialCompany !== undefined
  const contactLocked = initialContact !== undefined
  const [form, setForm] = useState<FormState>(() => ({
    // 딜은 회사 id 와 이름만 들고 있습니다. 아래에서 한 건을 읽어 채웁니다.
    company: initialCompany ? { kind: 'existing', company: initialCompany } : null,
    // 목록이 주는 것은 담당자의 id 와 이름뿐입니다. 칸에 이름만 보이면 되므로 나머지는
    // 비워 둡니다. 사람을 다시 고르면 온전한 값으로 덮입니다.
    contact:
      initialContact ??
      (deal?.contactId && deal.contactName
        ? {
            id: deal.contactId,
            name: deal.contactName,
            companyId: deal.customerCompanyId,
            org: '',
            dept: '',
            title: '',
          }
        : null),
    product: deal?.productId ? { id: deal.productId, label: deal.product } : null,
    title: deal?.title ?? '',
    stageId: stageId ?? columns[0]?.id ?? '',
  }))
  // 아직 없는 고객사·담당자는 이 자리에서 등록합니다. null 이면 등록 모달이 닫힌 상태입니다.
  const [creating, setCreating] = useState<{
    company: CompanySelection | null
    name: string
  } | null>(null)
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

  // 아직 없는 회사를 고른 것은 "여기 없으니 새로 만들겠다" 는 뜻입니다. 딜에는 담당자도
  // 필요하므로 회사만 만들어 두지 않고 고객 등록으로 넘겨 둘을 한 번에 만듭니다.
  const pickCompany = (next: CompanySelection | null) => {
    if (next?.kind === 'new') {
      setCreating({ company: next, name: '' })
      return
    }
    // 회사를 바꾸면 그 전 회사 사람이 담당자로 남아 있으면 안 됩니다.
    setForm((current) => ({ ...current, company: next, contact: null }))
    setErrors((current) => ({ ...current, company: undefined, contact: undefined }))
  }

  // 방금 등록한 담당자. 회사까지 함께 돌아오므로 두 칸이 한 번에 채워집니다.
  const takeCreated = async (contact: CustomerContactResponse) => {
    setCreating(null)
    set('contact', toContactOption(contact))

    // 고객사 칸은 회사 한 벌을 그대로 들고 있어야 해, 수정으로 열 때와 같이 읽어 옵니다.
    try {
      const { data } = await client.get<CustomerCompanyResponse>(
        `/customer-companies/${contact.company_id}`,
      )
      set('company', { kind: 'existing', company: data })
    } catch {
      // 회사를 못 읽어도 담당자는 이미 골라졌습니다. 칸만 비어 보입니다.
    }
  }

  const close = () => {
    if (!submittingRef.current) onClose()
  }

  const submit = async () => {
    if (submittingRef.current) return

    const found: Errors = {}
    const selectedCompanyId = companyId(form.company)
    if (selectedCompanyId === null) found.company = '고객사를 선택해 주세요.'
    // AI 가 다음 미팅을 추천할 때 일정에 적을 사람입니다. 비어 있으면 그 딜은 브리핑이
    // 만들어지지 않으므로 딜을 만들 때 함께 정합니다.
    if (form.contact === null) found.contact = '담당자를 선택해 주세요.'
    if (form.product === null) found.product = '제품을 선택해 주세요.'
    if (form.stageId === '') found.stageId = '파이프라인 단계를 선택해 주세요.'
    if (form.title.length > 254) found.title = '제목은 254자까지 입력할 수 있습니다.'

    setErrors(found)
    if (
      selectedCompanyId === null ||
      form.contact === null ||
      form.product === null ||
      Object.keys(found).length > 0
    )
      return

    submittingRef.current = true
    setSubmitting(true)
    setSubmitError(null)
    try {
      // 화면에서 묻지 않는 값입니다. 추가는 기본값으로, 수정은 원래 값 그대로 보냅니다.
      await onSubmit({
        customerCompanyId: selectedCompanyId,
        customerContactId: form.contact.id,
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
            invalid={errors.company !== undefined}
            disabled={submitting || companyLocked}
            value={form.company}
            onChange={pickCompany}
          />
        </Field>

        <Field label="담당자" required error={errors.contact}>
          <ContactPicker
            allowCreate
            label="담당자"
            placeholder={
              companyId(form.company) === null ? '고객사를 먼저 선택하세요' : '이름으로 검색'
            }
            companyId={companyId(form.company)}
            disabled={submitting || contactLocked}
            invalid={errors.contact !== undefined}
            value={form.contact}
            onChange={(next) => set('contact', next)}
            onCreate={(name) => setCreating({ company: form.company, name })}
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

      {/* 이 모달 본문은 <form> 이라 등록 폼을 그 안에 두면 폼이 겹칩니다. 바깥 스크림의
          backdrop-filter 도 fixed 자식의 기준 상자를 바꿔 위치가 어긋납니다. body 로 꺼냅니다. */}
      {creating &&
        createPortal(
          <CustomerFormModal
            onClose={() => setCreating(null)}
            onCreated={(contact) => void takeCreated(contact)}
            initial={{ name: creating.name }}
            initialCompany={creating.company ?? undefined}
          />,
          document.body,
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
