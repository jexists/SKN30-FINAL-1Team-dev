// 시연용 합성 데이터입니다. demo/layout_v3.html 에서 옮겼습니다.
import { addDays, iso, TODAY } from '@/utils/date'

import type { PurchaseOrder, PurchaseOrderSeed } from './types'

const purchaseOrderSeed: PurchaseOrderSeed[] = [
  {
    no: 'FM-PO-2026-0021',
    contract: 'FM-CT-2026-0038',
    hospital: '새봄정형외과',
    supplier: '본사 생산팀',
    orderedOff: -9,
    dueOff: 2,
    expectOff: 1,
    status: '출고',
    memo: '설치 공간 사전 확인 완료',
    items: [{ product: 'SonoFlex Pro', qty: 1, price: 28_400_000 }],
  },
  {
    no: 'FM-PO-2026-0020',
    contract: 'FM-CT-2026-0035',
    hospital: '한빛대학교병원',
    supplier: '본사 생산팀',
    orderedOff: -13,
    dueOff: 6,
    expectOff: 6,
    status: '생산중',
    memo: '분할 납품 1차',
    items: [{ product: 'CardioView X7', qty: 2, price: 24_000_000 }],
  },
  {
    no: 'FM-PO-2026-0019',
    contract: 'FM-CT-2026-0031',
    hospital: '서림메디컬센터',
    supplier: '외부 벤더 (메디파츠)',
    orderedOff: -21,
    dueOff: -7,
    expectOff: -8,
    status: '입고완료',
    memo: '',
    items: [{ product: 'OrthoScan Mini', qty: 3, price: 8_600_000 }],
  },
  {
    no: 'FM-PO-2026-0022',
    contract: '',
    hospital: '한빛대학교병원',
    supplier: '외부 벤더 (한성의료기)',
    orderedOff: -6,
    dueOff: 2,
    expectOff: 4,
    status: '승인대기',
    memo: '소모품 선발주',
    items: [{ product: '전극 패드 (소모품)', qty: 40, price: 32_000 }],
  },
  {
    no: 'FM-PO-2026-0023',
    contract: 'FM-CT-2026-0040',
    hospital: '정우병원',
    supplier: '본사 생산팀',
    orderedOff: -3,
    dueOff: 9,
    expectOff: 8,
    status: '출고의뢰서 작성완료',
    memo: '설치 공간 실측 대기',
    items: [{ product: 'OrthoScan Mini', qty: 2, price: 8_600_000 }],
  },
]

export const orders: PurchaseOrder[] = purchaseOrderSeed.map((o) => ({
  ...o,
  ordered: iso(addDays(TODAY, o.orderedOff)),
  due: iso(addDays(TODAY, o.dueOff)),
  expect: iso(addDays(TODAY, o.expectOff)),
}))

/** 예상 입고일이 납기를 넘긴 발주 */
export function isLate(o: PurchaseOrder): boolean {
  return o.expectOff > o.dueOff
}

/** 예상 입고까지 남은 일수. offset 이 이미 오늘 기준이라 그대로 씁니다. */
export function dday(o: PurchaseOrder): number {
  return o.expectOff
}

export function orderTotal(o: PurchaseOrder): number {
  return o.items.reduce((sum, it) => sum + it.qty * it.price, 0)
}

export function orderItemLabel(o: PurchaseOrder): string {
  return o.items.map((it) => `${it.product} ${it.qty}개`).join(', ')
}

export const activeOrders = (): PurchaseOrder[] => orders.filter((o) => o.status !== '취소')
