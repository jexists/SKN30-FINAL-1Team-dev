// 발주 입력값을 다루는 규칙입니다. 모달(OrderForm)과 추가 화면(New)이 같은 항목을
// 받으므로 검사와 변환을 여기 한 곳에 둡니다. 어느 쪽으로 넣든 결과가 같아야 합니다.
import type { ApiPurchaseOrder, OrderStatus } from '@/types'
import { addDays, iso, TODAY, TODAY_ISO } from '@/utils/date'

import type { OrderDraft } from './useOrderList'

// 입력값은 전부 문자열로 다룹니다. 지우는 도중 0 이 되어 버리지 않게 수량·단가도
// 문자열로 두고 제출할 때 한 번에 숫자로 돌립니다.
export interface ItemState {
  productId: string
  qty: string
  price: string
}

export interface FormState {
  customerCompanyId: string
  supplier: string
  contractId: string
  status: string
  ordered: string
  due: string
  expect: string
  memo: string
  items: ItemState[]
}

/** 품목 줄의 오류는 줄 번호별로 담습니다. 어느 줄이 잘못됐는지 알려야 합니다. */
export type ItemErrors = Record<number, Partial<Record<keyof ItemState, string>>>

export interface FormErrors extends Partial<Record<Exclude<keyof FormState, 'items'>, string>> {
  items?: string
  itemRows?: ItemErrors
}

export const emptyItem = (): ItemState => ({ productId: '', qty: '1', price: '' })

export function initialState(order?: ApiPurchaseOrder): FormState {
  return {
    customerCompanyId: order?.customerCompanyId ?? '',
    supplier: order?.supplier ?? '',
    contractId: order?.contractId ?? '',
    status: order?.status ?? '발주 접수',
    ordered: order?.ordered ?? TODAY_ISO,
    // 새 발주는 납기를 2주 뒤로 잡아 둡니다. 대부분 그 언저리라 고치는 손이 줄어듭니다.
    due: order?.due ?? iso(addDays(TODAY, 14)),
    expect: order?.expect ?? iso(addDays(TODAY, 14)),
    memo: order?.memo ?? '',
    items: order
      ? order.items.map((it) => ({
          productId: it.productId,
          qty: String(it.qty),
          price: String(it.price),
        }))
      : [emptyItem()],
  }
}

const num = (value: string) => Number(value.replace(/,/g, ''))

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

export function validate(form: FormState): FormErrors {
  const errors: FormErrors = {}
  if (form.customerCompanyId === '') errors.customerCompanyId = '고객사를 선택하세요.'
  if (form.supplier.trim() === '') errors.supplier = '공급처를 입력하세요.'

  if (!DATE_RE.test(form.ordered)) errors.ordered = '날짜를 선택하세요.'
  if (!DATE_RE.test(form.due)) errors.due = '날짜를 선택하세요.'
  if (!DATE_RE.test(form.expect)) errors.expect = '날짜를 선택하세요.'

  if (form.items.length === 0) errors.items = '품목을 한 줄 이상 넣으세요.'
  else if (form.items.length > 100) errors.items = '품목은 100개까지 넣을 수 있습니다.'

  const rows: ItemErrors = {}
  form.items.forEach((item, index) => {
    const row: Partial<Record<keyof ItemState, string>> = {}
    if (item.productId === '') row.productId = '제품을 선택하세요.'

    const qty = num(item.qty)
    if (!/^\d+$/.test(item.qty) || !Number.isSafeInteger(qty) || qty <= 0)
      row.qty = '1 이상의 정수로 입력하세요.'

    const price = num(item.price)
    if (!/^\d+$/.test(item.price) || !Number.isSafeInteger(price))
      row.price = '0 이상의 정수로 입력하세요.'

    if (Object.keys(row).length > 0) rows[index] = row
  })

  if (Object.keys(rows).length > 0) errors.itemRows = rows
  return errors
}

/** 합계 금액. 아직 다 못 채운 줄은 0 으로 봅니다. 입력하는 동안에도 보여야 합니다. */
export function totalOf(form: FormState): number {
  return form.items.reduce((sum, item) => {
    const qty = num(item.qty)
    const price = num(item.price)
    if (Number.isNaN(qty) || Number.isNaN(price)) return sum
    return sum + qty * price
  }, 0)
}

export function toDraft(form: FormState): OrderDraft {
  return {
    customerCompanyId: form.customerCompanyId,
    supplier: form.supplier.trim(),
    contractId: form.contractId || null,
    status: form.status as OrderStatus,
    ordered: form.ordered,
    due: form.due,
    expect: form.expect,
    memo: form.memo.trim() || null,
    items: form.items.map((item) => ({
      productId: item.productId,
      qty: num(item.qty),
      price: num(item.price),
    })),
  }
}
