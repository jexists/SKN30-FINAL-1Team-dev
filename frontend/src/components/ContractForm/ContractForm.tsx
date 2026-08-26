// 계약 작성·수정 모달입니다.
//
// 계약은 견적과 마찬가지로 딜의 한 국면이라 `PATCH /sales-deals/{id}` 로 저장합니다.
// 금액 칸은 견적금액에서 시작합니다. 계약은 견적가를 협의로 깎아 정하는 일이 많고,
// 저장은 quote_amount 가 아니라 contract_amount 로 들어가므로 견적가는 그대로 남습니다.
import { useRef, useState } from 'react'

import Button from '@/components/Button'
import Field from '@/components/FormField'
import Modal from '@/components/Modal'
import RecordPicker from '@/components/RecordPicker'
import { toSalesDeal, type SalesDeal } from '@/pages/Deals/useSalesDeals'
import type { DocumentStatusResponse, SalesDealDocumentFields, SalesDealResponse } from '@/types'
import { addDays, iso, TODAY, TODAY_ISO } from '@/utils/date'
import { formatBusinessNo, wonFull } from '@/utils/format'

import styles from './ContractForm.module.scss'

interface Props {
  /** 어느 딜의 계약인지. 주지 않으면 폼 안에서 딜부터 고릅니다. */
  deal?: SalesDeal
  statuses: DocumentStatusResponse[]
  onClose: () => void
  onSubmit: (dealId: string, fields: SalesDealDocumentFields) => Promise<void>
}

interface FormState {
  no: string
  signedOn: string
  endsOn: string
  statusCode: string
  amount: string
  warranty: string
  paymentTerms: string
  lateInterestTerms: string
}

/** 계약자정보 한 줄. 상호 옆에 사업자등록번호가 있으면 함께 적습니다. */
function party(name: string | null, businessNo: string | null): string {
  if (!name) return '-'
  const formatted = formatBusinessNo(businessNo)
  return formatted === null ? name : `${name} (${formatted})`
}

type Errors = Partial<Record<keyof FormState | 'deal', string>>

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

function initialState(deal: SalesDeal | undefined, statuses: DocumentStatusResponse[]): FormState {
  // 금액은 계약가 → 견적가 순으로 집습니다. 아직 계약가가 없으면 견적가에서 고칩니다.
  const amount = deal?.contractAmount ?? deal?.quoteAmount ?? null
  return {
    no: deal?.contractNo ?? '',
    signedOn: deal?.contractSignedOn ?? TODAY_ISO,
    // 계약 기간은 대개 1년입니다. 채워 두고 다르면 고치게 합니다.
    endsOn: deal?.contractEndsOn ?? iso(addDays(TODAY, 365)),
    statusCode: deal?.contractStatusCode ?? statuses[0]?.code ?? '',
    amount: amount === null ? '' : String(amount),
    warranty: deal?.warrantyTerms ?? '',
    paymentTerms: deal?.contractPaymentTerms ?? '',
    lateInterestTerms: deal?.contractLateInterestTerms ?? '',
  }
}

export default function ContractForm({ deal, statuses, onClose, onSubmit }: Props) {
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

  const close = () => {
    if (!submittingRef.current) onClose()
  }

  const submit = async () => {
    if (submittingRef.current) return

    const found: Errors = {}
    if (target === null) found.deal = '어느 딜의 계약인지 고르세요.'
    if (form.statusCode === '') found.statusCode = '계약 상태를 고르세요.'

    const amount = Number(form.amount)
    if (!/^\d+$/.test(form.amount) || !Number.isSafeInteger(amount))
      found.amount = '0 이상의 정수로 입력해 주세요.'

    if (!DATE_RE.test(form.signedOn)) found.signedOn = '계약일을 고르세요.'
    // 서버도 같은 순서를 봅니다. 먼저 알려 주어야 저장을 눌렀다가 되돌아오지 않습니다.
    else if (target && form.signedOn < target.date)
      found.signedOn = '계약일은 영업 시작일보다 앞설 수 없습니다.'
    if (!DATE_RE.test(form.endsOn)) found.endsOn = '계약 종료일을 고르세요.'
    else if (form.endsOn < form.signedOn)
      found.endsOn = '계약 종료일은 계약일보다 앞설 수 없습니다.'

    setErrors(found)
    if (target === null || Object.keys(found).length > 0) return

    submittingRef.current = true
    setSubmitting(true)
    setSubmitError(null)
    try {
      await onSubmit(target.id, {
        contract_no: form.no.trim() || null,
        contract_signed_on: form.signedOn,
        contract_ends_on: form.endsOn,
        contract_status_code: form.statusCode,
        contract_amount: amount,
        warranty_terms: form.warranty.trim() || null,
        contract_payment_terms: form.paymentTerms.trim() || null,
        contract_late_interest_terms: form.lateInterestTerms.trim() || null,
      })
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '계약을 저장하지 못했습니다.')
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  const editing = deal?.contractStatusCode != null

  return (
    <Modal
      title={editing ? '계약 수정' : '계약 작성'}
      description={
        target ? `${target.no} · ${target.org}` : '계약은 영업 딜에 붙습니다. 먼저 딜을 고르세요.'
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
                if (picked) setForm(initialState(picked, statuses))
              }}
            />
          </Field>
        )}

        <Field label="계약번호">
          <input
            value={form.no}
            disabled={submitting}
            maxLength={254}
            placeholder="비우면 딜 번호로 봅니다"
            onChange={(event) => set('no', event.target.value)}
          />
        </Field>

        <Field label="계약상태" required error={errors.statusCode}>
          <select
            value={form.statusCode}
            disabled={submitting || statuses.length === 0}
            onChange={(event) => set('statusCode', event.target.value)}
          >
            <option value="">계약 상태를 선택하세요</option>
            {statuses.map((status) => (
              <option key={status.id} value={status.code}>
                {status.name}
              </option>
            ))}
          </select>
        </Field>

        <Field label="계약금액 (원)" required error={errors.amount}>
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

        <Field label="계약일" required error={errors.signedOn}>
          <input
            type="date"
            value={form.signedOn}
            disabled={submitting}
            onChange={(event) => set('signedOn', event.target.value)}
          />
        </Field>

        <Field label="계약 종료일" required error={errors.endsOn}>
          <input
            type="date"
            value={form.endsOn}
            disabled={submitting}
            onChange={(event) => set('endsOn', event.target.value)}
          />
        </Field>

        {/* 계약자정보는 딜의 고객사와 팀에서 따라옵니다. 계약이 따로 적을 것이 아닙니다. */}
        <Field label="계약자정보 (갑)">
          <input
            value={target === null ? '' : party(target.org, target.companyBusinessNo)}
            readOnly
            disabled
            aria-label="계약자정보 (갑)"
          />
        </Field>

        <Field label="계약자정보 (을)">
          <input
            value={target === null ? '' : party(target.teamCompanyName, target.teamBusinessNo)}
            readOnly
            disabled
            aria-label="계약자정보 (을)"
          />
        </Field>

        {/* 납품예상일자와 품목은 견적이 넣어 둔 값입니다. 딜:견적:계약이 1:1 이라 같은 행에
            그대로 있고, 계약에서 고칠 것이 아니라 확인할 것이라 읽기 전용입니다. */}
        <Field label="납품예상일자" wide>
          <input
            value={target?.quoteDeliveryTerms ?? ''}
            readOnly
            disabled
            placeholder={target === null ? '' : '견적에 적지 않았습니다'}
            aria-label="납품예상일자"
          />
        </Field>

        <Field label="보증기간" wide>
          <textarea
            rows={2}
            value={form.warranty}
            disabled={submitting}
            maxLength={5000}
            placeholder="설치 후 1년 무상 보증"
            onChange={(event) => set('warranty', event.target.value)}
          />
        </Field>

        <Field label="물품대금 지급기일">
          <input
            value={form.paymentTerms}
            disabled={submitting}
            maxLength={254}
            placeholder="납품 후 30일 이내"
            onChange={(event) => set('paymentTerms', event.target.value)}
          />
        </Field>

        <Field label="대금연체 이자율">
          <input
            value={form.lateInterestTerms}
            disabled={submitting}
            maxLength={254}
            placeholder="상법 연이자 6%"
            onChange={(event) => set('lateInterestTerms', event.target.value)}
          />
        </Field>

        <div className={styles.items}>
          <div className={styles.itemsHead}>
            <span className={styles.itemsLabel}>품목</span>
            <span className={`${styles.itemsTotal} tnum`}>
              {target === null || target.quoteAmount === null ? '-' : wonFull(target.quoteAmount)}
            </span>
          </div>
          {target === null || target.items.length === 0 ? (
            <p className={styles.itemsEmpty}>
              {target === null ? '딜을 먼저 고르세요.' : '견적에 품목이 없습니다.'}
            </p>
          ) : (
            <ul className={styles.itemRows}>
              {target.items.map((item) => (
                <li key={item.id}>
                  <span>{item.product_name}</span>
                  <span className="tnum">{item.quantity}개</span>
                  <span className="tnum">{wonFull(item.unit_price)}</span>
                  <span className="tnum">{wonFull(item.quantity * item.unit_price)}</span>
                </li>
              ))}
            </ul>
          )}
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
