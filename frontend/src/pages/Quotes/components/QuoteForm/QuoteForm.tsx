// 견적 작성·수정 모달입니다.
//
// 견적은 딜의 한 국면이라 별도의 표가 아니라 `PATCH /sales-deals/{id}` 로 저장합니다.
// 그래서 먼저 어느 딜의 견적인지를 정해야 하고, 딜 상세에서 열면 이미 정해져 있습니다.
//
// 견적금액은 품목의 합입니다. 서버도 같은 값을 다시 계산하므로 여기 숫자는 미리보기입니다.
import { useRef, useState } from 'react'

import Button from '@/components/Button'
import ItemRows, {
  emptyItem,
  itemNumber,
  validateItems,
  type ItemErrors,
  type ItemState,
} from '@/components/ItemRows'
import Modal from '@/components/Modal'
import RecordPicker from '@/components/RecordPicker'
import type { DocumentStatusResponse, SalesDealDocumentFields, SalesDealResponse } from '@/types'
import {
  addMonthsKeepingDay,
  fmtDot,
  iso,
  parseISO,
  TODAY_ISO,
  wholeMonthsBetween,
} from '@/utils/date'

import Field from '@/components/FormField'
import { toSalesDeal, type SalesDeal } from '@/pages/Deals/useSalesDeals'

import styles from './QuoteForm.module.scss'

interface Props {
  /** 어느 딜의 견적인지. 주지 않으면 폼 안에서 딜부터 고릅니다. */
  deal?: SalesDeal
  statuses: DocumentStatusResponse[]
  onClose: () => void
  onSubmit: (dealId: string, fields: SalesDealDocumentFields) => Promise<void>
}

interface FormState {
  no: string
  issuedOn: string
  /** 개월 수. 빈 문자열이면 아래 validUntil 날짜를 직접 적는 것입니다. */
  validMonths: string
  validUntil: string
  statusCode: string
  deliveryTerms: string
  items: ItemState[]
}

type Errors = Partial<Record<keyof FormState | 'deal', string>> & { itemRows?: ItemErrors }

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

/** 견적 유효기간. 요구사항이 "ex) 1개월" 이라 기간으로 받고 날짜는 계산합니다. */
const VALID_MONTHS = ['1', '2', '3', '6'] as const
const DEFAULT_VALID_MONTHS = '1'
const CUSTOM_VALID = ''

const validUntilOf = (issuedOn: string, months: string) =>
  iso(addMonthsKeepingDay(parseISO(issuedOn), Number(months)))

function initialState(deal: SalesDeal | undefined, statuses: DocumentStatusResponse[]): FormState {
  const issuedOn = deal?.quoteIssuedOn ?? TODAY_ISO
  // 저장된 유효기한이 견적일에서 딱 떨어지는 개월이면 그 기간을 고른 채로 엽니다.
  // 아니면 직접 입력으로 열어야 예전에 적어 둔 날짜가 지워지지 않습니다.
  const saved =
    deal?.quoteValidUntil == null
      ? null
      : wholeMonthsBetween(parseISO(issuedOn), parseISO(deal.quoteValidUntil))
  const validMonths =
    deal?.quoteValidUntil == null
      ? DEFAULT_VALID_MONTHS
      : saved !== null && VALID_MONTHS.includes(String(saved) as (typeof VALID_MONTHS)[number])
        ? String(saved)
        : CUSTOM_VALID
  return {
    no: deal?.quoteNo ?? '',
    issuedOn,
    validMonths,
    validUntil:
      deal?.quoteValidUntil ?? validUntilOf(issuedOn, validMonths || DEFAULT_VALID_MONTHS),
    statusCode: deal?.quoteStatusCode ?? statuses[0]?.code ?? '',
    deliveryTerms: deal?.quoteDeliveryTerms ?? '',
    items:
      deal && deal.items.length > 0
        ? deal.items.map((item) => ({
            productId: item.product_id,
            productName: item.product_name,
            qty: String(item.quantity),
            price: String(item.unit_price),
          }))
        : [emptyItem()],
  }
}

export default function QuoteForm({ deal, statuses, onClose, onSubmit }: Props) {
  // 딜 상세에서 열면 이미 정해져 있고, 견적현황에서 바로 열면 여기서 고릅니다.
  const [target, setTarget] = useState<SalesDeal | null>(deal ?? null)
  const [form, setForm] = useState<FormState>(() => initialState(deal, statuses))
  const [errors, setErrors] = useState<Errors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const submittingRef = useRef(false)

  const set = <Key extends keyof FormState>(key: Key, value: FormState[Key]) => {
    setForm((current) => ({ ...current, [key]: value }))
    setErrors((current) => ({ ...current, [key]: undefined }))
  }

  /** 견적일이 움직이면 기간으로 고른 유효기한도 따라갑니다. 직접 입력은 그대로 둡니다. */
  const setIssuedOn = (issuedOn: string) =>
    setForm((current) => ({
      ...current,
      issuedOn,
      validUntil:
        current.validMonths !== CUSTOM_VALID && DATE_RE.test(issuedOn)
          ? validUntilOf(issuedOn, current.validMonths)
          : current.validUntil,
    }))

  const setValidMonths = (validMonths: string) =>
    setForm((current) => ({
      ...current,
      validMonths,
      validUntil:
        validMonths !== CUSTOM_VALID && DATE_RE.test(current.issuedOn)
          ? validUntilOf(current.issuedOn, validMonths)
          : current.validUntil,
    }))

  const close = () => {
    if (!submittingRef.current) onClose()
  }

  const submit = async () => {
    if (submittingRef.current) return

    const found: Errors = {}
    if (target === null) found.deal = '어느 딜의 견적인지 고르세요.'
    if (form.statusCode === '') found.statusCode = '견적 상태를 고르세요.'
    if (!DATE_RE.test(form.issuedOn)) found.issuedOn = '견적일을 고르세요.'
    // 서버도 같은 순서를 봅니다. 먼저 알려 주어야 저장을 눌렀다가 되돌아오지 않습니다.
    else if (target && form.issuedOn < target.date)
      found.issuedOn = '견적일은 영업 시작일보다 앞설 수 없습니다.'
    if (!DATE_RE.test(form.validUntil)) found.validUntil = '유효기한을 고르세요.'
    else if (form.validUntil < form.issuedOn)
      found.validUntil = '유효기한은 견적일보다 앞설 수 없습니다.'

    const { message, rows } = validateItems(form.items)
    if (message) found.items = message
    if (rows) found.itemRows = rows

    setErrors(found)
    if (target === null || Object.keys(found).length > 0) return

    submittingRef.current = true
    setSubmitting(true)
    setSubmitError(null)
    try {
      await onSubmit(target.id, {
        quote_no: form.no.trim() || null,
        quote_issued_on: form.issuedOn,
        quote_valid_until: form.validUntil,
        quote_status_code: form.statusCode,
        quote_delivery_terms: form.deliveryTerms.trim() || null,
        items: form.items.map((item) => ({
          product_id: item.productId,
          quantity: itemNumber(item.qty),
          unit_price: itemNumber(item.price),
        })),
      })
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '견적을 저장하지 못했습니다.')
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  const editing = deal?.quoteStatusCode != null

  return (
    <Modal
      title={editing ? '견적 수정' : '견적 작성'}
      description={
        target ? `${target.no} · ${target.org}` : '견적은 영업 딜에 붙습니다. 먼저 딜을 고르세요.'
      }
      onClose={close}
      onSubmit={() => void submit()}
      footer={
        <>
          <Button type="button" variant="outline" disabled={submitting} onClick={close}>
            취소
          </Button>
          <Button type="submit" disabled={submitting || statuses.length === 0}>
            {submitting ? '저장 중…' : '저장'}
          </Button>
        </>
      }
    >
      <div className={styles.grid}>
        {deal === undefined && (
          <Field label="영업 딜" required error={errors.deal} wide>
            <RecordPicker<SalesDealResponse>
              path="/sales-deals"
              label="영업 딜"
              placeholder="딜 번호나 고객사로 검색"
              params={{ sales_pipeline_status_code: ['published'] }}
              emptyText="일치하는 영업 딜이 없습니다."
              loadingText="영업 딜을 불러오는 중입니다."
              fallback="영업 딜을 불러오지 못했습니다."
              value={target === null ? null : { id: target.id, label: target.no, note: target.org }}
              disabled={submitting}
              invalid={errors.deal !== undefined}
              toOption={(row) => ({
                id: row.id,
                label: row.deal_no,
                note: row.customer_company_name,
              })}
              onChange={(_next, row) => {
                const picked = row === null ? null : toSalesDeal(row)
                setTarget(picked)
                setErrors((current) => ({ ...current, deal: undefined }))
                // 이미 견적이 있는 딜을 고르면 그 값에서 이어 씁니다.
                if (picked) setForm(initialState(picked, statuses))
              }}
            />
          </Field>
        )}

        <Field label="견적번호">
          <input
            value={form.no}
            disabled={submitting}
            maxLength={254}
            placeholder="비우면 딜 번호로 봅니다"
            onChange={(event) => set('no', event.target.value)}
          />
        </Field>

        <Field label="견적상태" required error={errors.statusCode}>
          <select
            value={form.statusCode}
            disabled={submitting || statuses.length === 0}
            onChange={(event) => set('statusCode', event.target.value)}
          >
            <option value="">견적 상태를 선택하세요</option>
            {statuses.map((status) => (
              <option key={status.id} value={status.code}>
                {status.name}
              </option>
            ))}
          </select>
        </Field>

        <Field label="견적일" required error={errors.issuedOn}>
          <input
            type="date"
            value={form.issuedOn}
            disabled={submitting}
            onChange={(event) => setIssuedOn(event.target.value)}
          />
        </Field>

        <Field label="견적 유효기간" required error={errors.validUntil}>
          <select
            value={form.validMonths}
            disabled={submitting}
            onChange={(event) => setValidMonths(event.target.value)}
          >
            {VALID_MONTHS.map((months) => (
              <option key={months} value={months}>
                {months}개월
              </option>
            ))}
            <option value={CUSTOM_VALID}>직접 입력</option>
          </select>
          {/* 저장하는 것은 날짜입니다. 고른 기간이 며칠까지인지 바로 보여 줍니다. */}
          {form.validMonths !== CUSTOM_VALID && (
            <span className={styles.hint}>
              {DATE_RE.test(form.validUntil)
                ? `${fmtDot(parseISO(form.validUntil))} 까지`
                : '견적일을 먼저 고르세요'}
            </span>
          )}
        </Field>

        {form.validMonths === CUSTOM_VALID && (
          <Field label="유효기한" required error={errors.validUntil}>
            <input
              type="date"
              value={form.validUntil}
              disabled={submitting}
              onChange={(event) => set('validUntil', event.target.value)}
            />
          </Field>
        )}

        {/* 견적을 내는 쪽과 받는 쪽은 딜에서 따라옵니다. 고를 것이 아닙니다. */}
        <Field label="견적업체명">
          <input value={target?.teamCompanyName ?? ''} readOnly disabled aria-label="견적업체명" />
        </Field>

        <Field label="견적수령업체">
          <input value={target?.org ?? ''} readOnly disabled aria-label="견적수령업체" />
        </Field>

        <Field label="납품예상일자" wide>
          <input
            value={form.deliveryTerms}
            disabled={submitting}
            maxLength={254}
            placeholder="계약완료 후 14일 이내"
            onChange={(event) => set('deliveryTerms', event.target.value)}
          />
        </Field>

        <div className={styles.wide}>
          <ItemRows
            items={form.items}
            error={errors.items}
            rows={errors.itemRows}
            disabled={submitting}
            onChange={(items) => set('items', items)}
          />
        </div>
      </div>

      {submitError && (
        <p className={styles.submitError} role="alert">
          {submitError}
        </p>
      )}
    </Modal>
  )
}
