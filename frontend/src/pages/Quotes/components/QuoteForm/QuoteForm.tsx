// 견적 추가·수정 모달입니다. quote 를 주면 수정, 주지 않으면 추가입니다.
// 항목 배치는 계약 폼(ContractFields)과 같고, 계약일 자리에 견적일·유효일수가 옵니다.
import { useState } from 'react'

import Button from '@/components/Button'
import { Field } from '@/components/ContractFields'
import Modal from '@/components/Modal'
import { KINDS, ORGS, OWNERS, PRODUCTS } from '@/shared/contracts'
import type { ContractKind, Quote, QuoteStageId } from '@/types'
import { TODAY_ISO } from '@/utils/date'

import { QUOTE_STAGES } from '../../stages'
import type { QuoteDraft } from '../../useQuoteList'

import styles from './QuoteForm.module.scss'

// 입력값은 전부 문자열로 다룹니다. 선택지는 제출할 때 원래 타입으로 돌립니다.
interface FormState {
  org: string
  product: string
  amount: string
  kind: string
  owner: string
  stageId: string
  date: string
  validDays: string
}

type FormErrors = Partial<Record<keyof FormState, string>>

interface Props {
  /** 수정할 견적. 없으면 새로 만듭니다. */
  quote?: Quote
  /** 새로 만들 때 시작할 단계 */
  stageId?: QuoteStageId
  onClose: () => void
  onSubmit: (draft: QuoteDraft) => void
  /** 수정할 때만 옵니다. 지우기 전 확인은 부르는 쪽이 합니다. */
  onDelete?: () => void
}

export default function QuoteForm({ quote, stageId, onClose, onSubmit, onDelete }: Props) {
  const [form, setForm] = useState<FormState>(() => ({
    org: quote?.org ?? '',
    product: quote?.product ?? '',
    // 금액은 입력 중에 숫자로 바꾸지 않습니다. 지우는 도중 0 이 되어 버립니다.
    amount: quote ? String(quote.amount) : '',
    kind: quote?.kind ?? KINDS[0],
    owner: quote?.owner ?? OWNERS[0],
    stageId: quote?.stageId ?? stageId ?? QUOTE_STAGES[0].id,
    date: quote?.date ?? TODAY_ISO,
    validDays: String(quote?.validDays ?? 30),
  }))
  const [errors, setErrors] = useState<FormErrors>({})

  const set = (key: keyof FormState, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const submit = () => {
    const found: FormErrors = {}
    if (form.org.trim() === '') found.org = '고객사를 입력하세요.'
    if (form.product.trim() === '') found.product = '제품을 입력하세요.'

    const amount = Number(form.amount.replace(/,/g, ''))
    if (form.amount.trim() === '') found.amount = '금액을 입력하세요.'
    else if (Number.isNaN(amount) || amount <= 0) found.amount = '0보다 큰 숫자로 입력하세요.'

    const validDays = Number(form.validDays)
    if (!Number.isInteger(validDays) || validDays <= 0) found.validDays = '1 이상으로 입력하세요.'

    if (!/^\d{4}-\d{2}-\d{2}$/.test(form.date)) found.date = '날짜를 선택하세요.'

    setErrors(found)
    if (Object.keys(found).length > 0) return

    onSubmit({
      org: form.org.trim(),
      product: form.product.trim(),
      amount,
      kind: form.kind as ContractKind,
      owner: form.owner,
      stageId: form.stageId as QuoteStageId,
      date: form.date,
      validDays,
    })
  }

  const editing = quote !== undefined

  return (
    <Modal
      title={editing ? '견적 수정' : '견적 추가'}
      description={editing ? quote.no : '견적번호는 저장할 때 자동으로 매깁니다.'}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          {onDelete && (
            <Button type="button" variant="ghost" onClick={onDelete}>
              삭제
            </Button>
          )}
          <Button type="button" variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button type="submit">{editing ? '저장' : '견적 추가'}</Button>
        </>
      }
    >
      <div className={styles.grid}>
        <Field label="고객사" required error={errors.org}>
          {/* 목록에 없는 곳도 새로 적을 수 있어야 해서 select 가 아니라 datalist 입니다. */}
          <input
            list="quote-orgs"
            value={form.org}
            placeholder="한빛대학교병원"
            onChange={(e) => set('org', e.target.value)}
          />
          <datalist id="quote-orgs">
            {ORGS.map((org) => (
              <option key={org} value={org} />
            ))}
          </datalist>
        </Field>

        <Field label="제품" required error={errors.product}>
          <input
            list="quote-products"
            value={form.product}
            placeholder="SonoFlex Pro"
            onChange={(e) => set('product', e.target.value)}
          />
          <datalist id="quote-products">
            {PRODUCTS.map((product) => (
              <option key={product} value={product} />
            ))}
          </datalist>
        </Field>

        <Field label="금액 (원)" required error={errors.amount}>
          <input
            inputMode="numeric"
            value={form.amount}
            placeholder="28400000"
            onChange={(e) => set('amount', e.target.value)}
          />
        </Field>

        <Field label="유형">
          <select value={form.kind} onChange={(e) => set('kind', e.target.value)}>
            {KINDS.map((kind) => (
              <option key={kind}>{kind}</option>
            ))}
          </select>
        </Field>

        <Field label="담당 영업">
          <select value={form.owner} onChange={(e) => set('owner', e.target.value)}>
            {OWNERS.map((owner) => (
              <option key={owner}>{owner}</option>
            ))}
          </select>
        </Field>

        <Field label="단계">
          <select value={form.stageId} onChange={(e) => set('stageId', e.target.value)}>
            {QUOTE_STAGES.map((stage) => (
              <option key={stage.id} value={stage.id}>
                {stage.name}
              </option>
            ))}
          </select>
        </Field>

        <Field label="견적일" error={errors.date}>
          <input type="date" value={form.date} onChange={(e) => set('date', e.target.value)} />
        </Field>

        <Field label="유효기간 (일)" error={errors.validDays}>
          <input
            inputMode="numeric"
            value={form.validDays}
            onChange={(e) => set('validDays', e.target.value)}
          />
        </Field>
      </div>
    </Modal>
  )
}
