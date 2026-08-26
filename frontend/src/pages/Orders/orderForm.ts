// 발주 입력값을 다루는 규칙입니다. 모달(OrderForm)과 추가 화면(New)이 같은 항목을
// 받으므로 검사와 변환을 여기 한 곳에 둡니다. 어느 쪽으로 넣든 결과가 같아야 합니다.
import {
  emptyItem,
  itemNumber,
  validateItems,
  type ItemErrors,
  type ItemState,
} from '@/components/ItemRows'
import type { ApiPurchaseOrder } from '@/types'
import { addDays, iso, TODAY, TODAY_ISO } from '@/utils/date'

import type { OrderDraft } from './useOrderList'

export type { ItemState } from '@/components/ItemRows'

export interface FormState {
  supplier: string
  salesDealId: string
  /** 고른 딜의 표시 글자. productName 과 같은 이유로 듭니다. */
  salesDealLabel: string
  stageCode: string
  ordered: string
  due: string
  expect: string
  requestDepartment: string
  cooperationDepartment: string
  expectedCompanyId: string
  /** 고른 거래처의 이름. salesDealLabel 과 같은 이유로 듭니다. */
  expectedCompanyLabel: string
  memo: string
  items: ItemState[]
}

// 발주서 양식에 박혀 있는 두 부서입니다. 거의 늘 이 값이라 채워 두고 고치게 합니다.
export const DEFAULT_REQUEST_DEPARTMENT = '영업팀'
export const DEFAULT_COOPERATION_DEPARTMENT = '생산팀'

export interface FormErrors extends Partial<Record<Exclude<keyof FormState, 'items'>, string>> {
  items?: string
  itemRows?: ItemErrors
}

export function initialState(order?: ApiPurchaseOrder): FormState {
  return {
    supplier: order?.supplier ?? '',
    salesDealId: order?.salesDealId ?? '',
    salesDealLabel: order?.salesDeal ?? '',
    stageCode: order?.stageCode ?? '',
    ordered: order?.ordered ?? TODAY_ISO,
    // 새 발주는 납기를 2주 뒤로 잡아 둡니다. 대부분 그 언저리라 고치는 손이 줄어듭니다.
    due: order?.due ?? iso(addDays(TODAY, 14)),
    expect: order?.expect ?? iso(addDays(TODAY, 14)),
    requestDepartment: order?.requestDepartment ?? DEFAULT_REQUEST_DEPARTMENT,
    cooperationDepartment: order?.cooperationDepartment ?? DEFAULT_COOPERATION_DEPARTMENT,
    expectedCompanyId: order?.expectedCustomerCompanyId ?? '',
    expectedCompanyLabel: order?.expectedCustomerCompany ?? '',
    memo: order?.memo ?? '',
    items: order
      ? order.items.map((it) => ({
          productId: it.productId,
          productName: it.product,
          qty: String(it.qty),
          price: String(it.price),
        }))
      : [emptyItem()],
  }
}

const num = itemNumber

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

export function validate(form: FormState): FormErrors {
  const errors: FormErrors = {}
  if (form.salesDealId === '') errors.salesDealId = '영업 딜을 선택하세요.'
  if (form.stageCode === '') errors.stageCode = '발주 상태를 선택하세요.'
  if (form.supplier.trim() === '') errors.supplier = '공급처를 입력하세요.'
  if (form.requestDepartment.trim() === '') errors.requestDepartment = '요청부서를 입력하세요.'
  if (form.cooperationDepartment.trim() === '')
    errors.cooperationDepartment = '협조부서를 입력하세요.'
  if (form.expectedCompanyId === '') errors.expectedCompanyId = '납품예상 거래처를 고르세요.'

  if (!DATE_RE.test(form.ordered)) errors.ordered = '날짜를 선택하세요.'
  if (!DATE_RE.test(form.due)) errors.due = '날짜를 선택하세요.'
  if (!DATE_RE.test(form.expect)) errors.expect = '날짜를 선택하세요.'

  const { message, rows } = validateItems(form.items)
  if (message) errors.items = message
  if (rows) errors.itemRows = rows
  return errors
}

export function toDraft(form: FormState): OrderDraft {
  return {
    supplier: form.supplier.trim(),
    salesDealId: form.salesDealId,
    stageCode: form.stageCode,
    ordered: form.ordered,
    due: form.due,
    expect: form.expect,
    requestDepartment: form.requestDepartment.trim(),
    cooperationDepartment: form.cooperationDepartment.trim(),
    expectedCustomerCompanyId: form.expectedCompanyId,
    memo: form.memo.trim() || null,
    items: form.items.map((item) => ({
      productId: item.productId,
      qty: num(item.qty),
      price: num(item.price),
    })),
  }
}
