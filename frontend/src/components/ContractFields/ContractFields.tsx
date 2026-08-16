// 계약 입력 항목입니다. 모달과 추가 화면이 같은 항목을 받으므로 배치도 하나로 둡니다.
// 화면마다 다른 항목(예: 단계)은 children 으로 뒤에 붙입니다.
import type { ReactNode } from 'react'

import { KINDS, ORGS, OWNERS, PRODUCTS } from '@/shared/contracts'

import type { FormErrors, FormState } from '../ContractForm/form'

import styles from './ContractFields.module.scss'

interface Props {
  form: FormState
  errors: FormErrors
  onChange: (key: keyof FormState, value: string) => void
  /** 메모 앞에 들어갈 추가 항목 */
  children?: ReactNode
}

export default function ContractFields({ form, errors, onChange, children }: Props) {
  return (
    <div className={styles.grid}>
      <Field label="고객사" required error={errors.org}>
        {/* 목록에 없는 곳도 새로 적을 수 있어야 해서 select 가 아니라 datalist 입니다. */}
        <input
          list="contract-orgs"
          value={form.org}
          placeholder="한빛대학교병원"
          onChange={(e) => onChange('org', e.target.value)}
        />
        <datalist id="contract-orgs">
          {ORGS.map((org) => (
            <option key={org} value={org} />
          ))}
        </datalist>
      </Field>

      <Field label="제품" required error={errors.product}>
        <input
          list="contract-products"
          value={form.product}
          placeholder="SonoFlex Pro"
          onChange={(e) => onChange('product', e.target.value)}
        />
        <datalist id="contract-products">
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
          onChange={(e) => onChange('amount', e.target.value)}
        />
      </Field>

      <Field label="유형">
        <select value={form.kind} onChange={(e) => onChange('kind', e.target.value)}>
          {KINDS.map((kind) => (
            <option key={kind}>{kind}</option>
          ))}
        </select>
      </Field>

      <Field label="담당 영업">
        <select value={form.owner} onChange={(e) => onChange('owner', e.target.value)}>
          {OWNERS.map((owner) => (
            <option key={owner}>{owner}</option>
          ))}
        </select>
      </Field>

      <Field label="계약일" error={errors.date}>
        <input type="date" value={form.date} onChange={(e) => onChange('date', e.target.value)} />
      </Field>

      {children}

      <Field label="메모" wide>
        <textarea
          rows={3}
          value={form.memo}
          placeholder="다음에 확인할 것"
          onChange={(e) => onChange('memo', e.target.value)}
        />
      </Field>
    </div>
  )
}

interface FieldProps {
  label: string
  required?: boolean
  error?: string
  wide?: boolean
  children: ReactNode
}

export function Field({ label, required, error, wide, children }: FieldProps) {
  return (
    <label className={[styles.field, wide ? styles.isWide : ''].filter(Boolean).join(' ')}>
      <span className={styles.label}>
        {label}
        {required && <b aria-hidden="true">*</b>}
      </span>
      {children}
      {error && <span className={styles.error}>{error}</span>}
    </label>
  )
}
