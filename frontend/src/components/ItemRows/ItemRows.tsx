// 제품·수량·단가를 줄 단위로 받는 표입니다. 발주와 견적이 같은 것을 씁니다.
//
// 줄 수가 정해져 있지 않아 나머지 입력 항목과 따로 다룹니다. 한 건에 여러 제품이
// 들어가는 일이 흔해서 한 줄로 고정할 수 없습니다.
import RecordPicker from '@/components/RecordPicker'
import { TrashIcon } from '@/components/icons'
import type { ProductResponse } from '@/types'
import { wonFull } from '@/utils/format'

import { emptyItem, itemNumber, totalOf, type ItemErrors, type ItemState } from './items'

import styles from './ItemRows.module.scss'

interface Props {
  items: ItemState[]
  onChange: (items: ItemState[]) => void
  /** 줄 수 자체의 문제 */
  error?: string
  /** 줄별 문제 */
  rows?: ItemErrors
  disabled?: boolean
}

/** 아직 다 못 채운 줄은 비워 둡니다. 입력하는 중에 0원이라고 우기지 않습니다. */
function rowAmount(item: ItemState): string {
  const qty = itemNumber(item.qty)
  const price = itemNumber(item.price)
  if (item.qty === '' || item.price === '' || Number.isNaN(qty) || Number.isNaN(price)) return '-'
  return wonFull(qty * price)
}

export default function ItemRows({ items, onChange, error, rows, disabled = false }: Props) {
  const setItem = (index: number, key: keyof ItemState, value: string) =>
    onChange(items.map((item, i) => (i === index ? { ...item, [key]: value } : item)))

  /** 제품은 id 와 이름을 함께 갈아 끼웁니다. 둘이 어긋나면 칸에 남는 글자가 거짓말을 합니다. */
  const setItemProduct = (index: number, productId: string, productName: string) =>
    onChange(items.map((item, i) => (i === index ? { ...item, productId, productName } : item)))

  return (
    <div className={styles.root}>
      <div className={styles.head}>
        <span className={styles.label}>
          품목
          <b aria-hidden="true">*</b>
        </span>
        <span className={`${styles.total} tnum`}>{wonFull(totalOf(items))}</span>
      </div>

      <ul className={styles.items}>
        {items.map((item, index) => {
          const row = rows?.[index]
          return (
            // 줄에는 고유한 값이 없어 자리로 셉니다. 입력값이 전부 state 에 있어
            // 줄을 지워도 남은 줄이 제 값을 그대로 들고 있습니다.
            <li key={index} className={styles.item}>
              <div className={styles.itemRow}>
                <div className={styles.product}>
                  <RecordPicker<ProductResponse>
                    path="/products"
                    label={`품목 ${index + 1} 제품`}
                    placeholder="제품 검색"
                    emptyText="일치하는 제품이 없습니다."
                    loadingText="제품을 불러오는 중입니다."
                    fallback="제품을 불러오지 못했습니다."
                    value={
                      item.productId === '' ? null : { id: item.productId, label: item.productName }
                    }
                    disabled={disabled}
                    invalid={row?.productId !== undefined}
                    toOption={(found) => ({ id: found.id, label: found.name })}
                    onChange={(next) => setItemProduct(index, next?.id ?? '', next?.label ?? '')}
                  />
                </div>
                <input
                  className={styles.qty}
                  inputMode="numeric"
                  value={item.qty}
                  disabled={disabled}
                  placeholder="수량"
                  aria-label={`품목 ${index + 1} 수량`}
                  onChange={(e) => setItem(index, 'qty', e.target.value)}
                />
                <input
                  className={styles.price}
                  inputMode="numeric"
                  value={item.price}
                  disabled={disabled}
                  placeholder="단가"
                  aria-label={`품목 ${index + 1} 단가`}
                  onChange={(e) => setItem(index, 'price', e.target.value)}
                />
                {/* 금액은 수량 × 단가라 고를 것이 없습니다. 보여 주기만 합니다. */}
                <span className={`${styles.amount} tnum`}>{rowAmount(item)}</span>
                {/* 마지막 한 줄은 지우지 않습니다. 품목 없는 발주·견적은 없습니다. */}
                <button
                  type="button"
                  className={styles.remove}
                  aria-label={`품목 ${index + 1} 삭제`}
                  disabled={disabled || items.length === 1}
                  onClick={() => onChange(items.filter((_, i) => i !== index))}
                >
                  <TrashIcon width={14} height={14} />
                </button>
              </div>
              {row && <span className={styles.error}>{row.productId ?? row.qty ?? row.price}</span>}
            </li>
          )
        })}
      </ul>

      <button
        type="button"
        className={styles.addItem}
        disabled={disabled || items.length >= 100}
        onClick={() => onChange([...items, emptyItem()])}
      >
        + 품목 추가
      </button>

      {error && <span className={styles.error}>{error}</span>}
    </div>
  )
}
