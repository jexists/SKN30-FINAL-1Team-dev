// 계약 입력값을 다루는 규칙입니다. 모달(ContractForm)과 추가 화면(New)이 같은 항목을
// 받으므로 검사와 변환을 여기 한 곳에 둡니다. 어느 쪽으로 넣든 결과가 같아야 합니다.
import { KINDS, OWNERS } from '@/shared/contracts'
import type { Contract, ContractDraft, ContractKind } from '@/types'
import { TODAY_ISO } from '@/utils/date'

// 입력값은 전부 문자열로 다룹니다. 선택지는 제출할 때 원래 타입으로 돌립니다.
export interface FormState {
  org: string
  product: string
  amount: string
  kind: string
  owner: string
  date: string
  memo: string
}

export type FormErrors = Partial<Record<keyof FormState, string>>

export function initialState(contract?: Contract): FormState {
  return {
    org: contract?.org ?? '',
    product: contract?.product ?? '',
    // 금액은 입력 중에 숫자로 바꾸지 않습니다. 지우는 도중 0 이 되어 버립니다.
    amount: contract ? String(contract.amount) : '',
    kind: contract?.kind ?? KINDS[0],
    owner: contract?.owner ?? OWNERS[0],
    date: contract?.date ?? TODAY_ISO,
    memo: contract?.memo ?? '',
  }
}

export function validate(form: FormState): FormErrors {
  const errors: FormErrors = {}
  if (form.org.trim() === '') errors.org = '고객사를 입력하세요.'
  if (form.product.trim() === '') errors.product = '제품을 입력하세요.'

  const amount = Number(form.amount.replace(/,/g, ''))
  if (form.amount.trim() === '') errors.amount = '금액을 입력하세요.'
  else if (Number.isNaN(amount) || amount <= 0) errors.amount = '0보다 큰 숫자로 입력하세요.'

  if (!/^\d{4}-\d{2}-\d{2}$/.test(form.date)) errors.date = '날짜를 선택하세요.'
  return errors
}

export function toDraft(form: FormState): ContractDraft {
  return {
    org: form.org.trim(),
    product: form.product.trim(),
    amount: Number(form.amount.replace(/,/g, '')),
    kind: form.kind as ContractKind,
    owner: form.owner,
    date: form.date,
    memo: form.memo.trim(),
  }
}
