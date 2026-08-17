// 발주 입력 항목입니다. 모달(OrderForm)과 추가 화면(New)이 같은 항목을 받으므로
// 배치도 하나로 둡니다. 화면마다 다른 항목은 children 으로 뒤에 붙습니다.
//
// 품목은 줄 수가 정해져 있지 않아 나머지 항목과 따로 다룹니다. 발주 한 건에
// 여러 제품이 들어가는 일이 흔해서 한 줄로 고정할 수 없습니다.
import type { ReactNode } from 'react'

import { TrashIcon } from '@/components/icons'
import type { PurchaseOrderStatusResponse } from '@/types'
import { wonFull } from '@/utils/format'

import {
  emptyItem,
  totalOf,
  type FormErrors,
  type FormState,
  type ItemState,
} from '../../orderForm'
import type { OrderSalesDealOption, OrderOption } from '../../useOrderList'

import styles from './OrderFields.module.scss'

interface Props {
  form: FormState
  errors: FormErrors
  onChange: (key: Exclude<keyof FormState, 'items'>, value: string) => void
  onItemsChange: (items: ItemState[]) => void
  salesDeals: OrderSalesDealOption[]
  statuses: PurchaseOrderStatusResponse[]
  products: OrderOption[]
  suppliers: string[]
  optionsLoading?: boolean
  disabled?: boolean
  showStatus?: boolean
  lockSalesDeal?: boolean
  /** 메모 앞에 들어갈 추가 항목 */
  children?: ReactNode
}

export default function OrderFields({
  form,
  errors,
  onChange,
  onItemsChange,
  salesDeals,
  statuses,
  products,
  suppliers,
  optionsLoading = false,
  disabled = false,
  showStatus = true,
  lockSalesDeal = false,
  children,
}: Props) {
  const setItem = (index: number, key: keyof ItemState, value: string) =>
    onItemsChange(form.items.map((item, i) => (i === index ? { ...item, [key]: value } : item)))

  return (
    <div className={styles.grid}>
      <Field label="영업 딜" required error={errors.salesDealId}>
        <select
          value={form.salesDealId}
          disabled={disabled || lockSalesDeal || optionsLoading || salesDeals.length === 0}
          onChange={(event) => onChange('salesDealId', event.target.value)}
        >
          <option value="">
            {optionsLoading
              ? '영업 딜을 불러오는 중…'
              : salesDeals.length === 0
                ? '선택할 영업 딜이 없습니다'
                : '영업 딜을 선택하세요'}
          </option>
          {salesDeals.map((salesDeal) => (
            <option key={salesDeal.id} value={salesDeal.id}>
              {salesDeal.no} · {salesDeal.customerCompanyName}
            </option>
          ))}
        </select>
      </Field>

      <Field label="공급처" required error={errors.supplier}>
        <input
          list="order-suppliers"
          value={form.supplier}
          disabled={disabled}
          maxLength={254}
          placeholder="본사 생산팀"
          onChange={(e) => onChange('supplier', e.target.value)}
        />
        <datalist id="order-suppliers">
          {suppliers.map((supplier) => (
            <option key={supplier} value={supplier} />
          ))}
        </datalist>
      </Field>

      {showStatus && (
        <Field label="상태" required error={errors.stageCode}>
          <select
            value={form.stageCode}
            disabled={disabled || optionsLoading || statuses.length === 0}
            onChange={(e) => onChange('stageCode', e.target.value)}
          >
            <option value="">발주 상태를 선택하세요</option>
            {statuses.map((status) => (
              <option key={status.id} value={status.code}>
                {status.name}
              </option>
            ))}
          </select>
        </Field>
      )}

      <Field label="발주일" error={errors.ordered}>
        <input
          type="date"
          value={form.ordered}
          disabled={disabled}
          onChange={(e) => onChange('ordered', e.target.value)}
        />
      </Field>

      <Field label="납기" error={errors.due}>
        <input
          type="date"
          value={form.due}
          disabled={disabled}
          onChange={(e) => onChange('due', e.target.value)}
        />
      </Field>

      <Field label="예상 입고" error={errors.expect}>
        <input
          type="date"
          value={form.expect}
          disabled={disabled}
          onChange={(e) => onChange('expect', e.target.value)}
        />
      </Field>

      {children}

      <div className={`${styles.field} ${styles.isWide}`}>
        <div className={styles.itemsHead}>
          <span className={styles.label}>
            품목
            <b aria-hidden="true">*</b>
          </span>
          <span className={`${styles.total} tnum`}>{wonFull(totalOf(form))}</span>
        </div>

        <ul className={styles.items}>
          {form.items.map((item, index) => {
            const row = errors.itemRows?.[index]
            return (
              // 줄에는 고유한 값이 없어 자리로 셉니다. 입력값이 전부 state 에 있어
              // 줄을 지워도 남은 줄이 제 값을 그대로 들고 있습니다.
              <li key={index} className={styles.item}>
                <div className={styles.itemRow}>
                  <select
                    className={styles.product}
                    value={item.productId}
                    disabled={disabled || optionsLoading || products.length === 0}
                    aria-label={`품목 ${index + 1} 제품`}
                    onChange={(e) => setItem(index, 'productId', e.target.value)}
                  >
                    <option value="">
                      {optionsLoading
                        ? '제품을 불러오는 중…'
                        : products.length === 0
                          ? '등록된 제품이 없습니다'
                          : '제품 선택'}
                    </option>
                    {products.map((product) => (
                      <option key={product.id} value={product.id}>
                        {product.name}
                      </option>
                    ))}
                  </select>
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
                  {/* 마지막 한 줄은 지우지 않습니다. 품목 없는 발주는 없습니다. */}
                  <button
                    type="button"
                    className={styles.remove}
                    aria-label={`품목 ${index + 1} 삭제`}
                    disabled={disabled || form.items.length === 1}
                    onClick={() => onItemsChange(form.items.filter((_, i) => i !== index))}
                  >
                    <TrashIcon width={14} height={14} />
                  </button>
                </div>
                {row && (
                  <span className={styles.error}>{row.productId ?? row.qty ?? row.price}</span>
                )}
              </li>
            )
          })}
        </ul>

        <button
          type="button"
          className={styles.addItem}
          disabled={disabled || optionsLoading || products.length === 0 || form.items.length >= 100}
          onClick={() => onItemsChange([...form.items, emptyItem()])}
        >
          + 품목 추가
        </button>

        {errors.items && <span className={styles.error}>{errors.items}</span>}
      </div>

      <Field label="메모" wide>
        <textarea
          rows={3}
          value={form.memo}
          disabled={disabled}
          maxLength={5000}
          placeholder="설치 공간 사전 확인 완료"
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
