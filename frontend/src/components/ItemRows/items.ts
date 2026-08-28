// 품목 줄을 다루는 규칙입니다. 발주와 견적이 같은 표를 쓰므로 검사와 합계를 여기 둡니다.
//
// 입력값은 전부 문자열로 다룹니다. 지우는 도중 0 이 되어 버리지 않게 수량·단가도
// 문자열로 두고 제출할 때 한 번에 숫자로 돌립니다.
export interface ItemState {
  productId: string
  /** 고른 제품의 이름. 검색해서 고르는 칸이 글자를 남겨야 해 함께 듭니다. 제출에는 쓰지 않습니다. */
  productName: string
  qty: string
  price: string
}

/** 품목 줄의 오류는 줄 번호별로 담습니다. 어느 줄이 잘못됐는지 알려야 합니다. */
export type ItemErrors = Record<number, Partial<Record<keyof ItemState, string>>>

export const emptyItem = (): ItemState => ({ productId: '', productName: '', qty: '1', price: '' })

export const itemNumber = (value: string) => Number(value.replace(/,/g, ''))

/** 합계 금액. 아직 다 못 채운 줄은 0 으로 봅니다. 입력하는 동안에도 보여야 합니다. */
export function totalOf(items: ItemState[]): number {
  return items.reduce((sum, item) => {
    const qty = itemNumber(item.qty)
    const price = itemNumber(item.price)
    if (Number.isNaN(qty) || Number.isNaN(price)) return sum
    return sum + qty * price
  }, 0)
}

/** 줄 수 자체의 문제와 줄별 문제를 나눠 돌려 줍니다. 부르는 쪽의 오류 모양이 서로 다릅니다. */
export function validateItems(items: ItemState[]): { message?: string; rows?: ItemErrors } {
  const message =
    items.length === 0
      ? '품목을 한 줄 이상 넣으세요.'
      : items.length > 100
        ? '품목은 100개까지 넣을 수 있습니다.'
        : undefined

  const rows: ItemErrors = {}
  items.forEach((item, index) => {
    const row: Partial<Record<keyof ItemState, string>> = {}
    if (item.productId === '') row.productId = '제품을 선택하세요.'

    const qty = itemNumber(item.qty)
    if (!/^\d+$/.test(item.qty) || !Number.isSafeInteger(qty) || qty <= 0)
      row.qty = '1 이상의 정수로 입력하세요.'

    const price = itemNumber(item.price)
    if (!/^\d+$/.test(item.price) || !Number.isSafeInteger(price))
      row.price = '0 이상의 정수로 입력하세요.'

    if (Object.keys(row).length > 0) rows[index] = row
  })

  return { message, ...(Object.keys(rows).length > 0 ? { rows } : {}) }
}
