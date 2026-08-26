// 발주 입력 항목입니다. 모달(OrderForm)과 추가 화면(New)이 같은 항목을 받으므로
// 배치도 하나로 둡니다. 화면마다 다른 항목은 children 으로 뒤에 붙습니다.
//
// 품목은 줄 수가 정해져 있지 않아 나머지 항목과 따로 다룹니다. 발주 한 건에
// 여러 제품이 들어가는 일이 흔해서 한 줄로 고정할 수 없습니다.
import type { ReactNode } from 'react'

import FormField from '@/components/FormField'
import ItemRows, { type ItemState } from '@/components/ItemRows'
import RecordPicker from '@/components/RecordPicker'
import type {
  CustomerCompanyResponse,
  PurchaseOrderStatusResponse,
  SalesDealResponse,
} from '@/types'

import { type FormErrors, type FormState } from '../../orderForm'
import styles from './OrderFields.module.scss'

interface Props {
  form: FormState
  errors: FormErrors
  onChange: (key: Exclude<keyof FormState, 'items'>, value: string) => void
  onItemsChange: (items: ItemState[]) => void
  statuses: PurchaseOrderStatusResponse[]
  suppliers: string[]
  optionsLoading?: boolean
  disabled?: boolean
  showStatus?: boolean
  lockSalesDeal?: boolean
  /** 작성자. 서버가 로그인한 사람으로 채우므로 여기서는 보여 주기만 합니다. */
  createdBy: string
  /** 메모 앞에 들어갈 추가 항목 */
  children?: ReactNode
}

export default function OrderFields({
  form,
  errors,
  onChange,
  onItemsChange,
  statuses,
  suppliers,
  optionsLoading = false,
  disabled = false,
  showStatus = true,
  lockSalesDeal = false,
  createdBy,
  children,
}: Props) {
  return (
    <div className={styles.grid}>
      <Field label="영업 딜" required error={errors.salesDealId}>
        <RecordPicker<SalesDealResponse>
          path="/sales-deals"
          label="영업 딜"
          placeholder="딜 번호나 고객사로 검색"
          // 보관된 파이프라인의 딜에는 새 발주를 붙이지 않습니다. 예전에는 전건을 받아
          // 화면에서 걸렀는데, 쪽으로 끊는 지금은 서버가 걸러야 첫 쪽이 맞습니다.
          params={{ sales_pipeline_status_code: ['published'] }}
          emptyText="일치하는 영업 딜이 없습니다."
          loadingText="영업 딜을 불러오는 중입니다."
          fallback="영업 딜을 불러오지 못했습니다."
          value={
            form.salesDealId === '' ? null : { id: form.salesDealId, label: form.salesDealLabel }
          }
          disabled={disabled || lockSalesDeal}
          invalid={errors.salesDealId !== undefined}
          toOption={(row) => ({
            id: row.id,
            label: row.deal_no,
            note: row.customer_company_name,
          })}
          onChange={(next, row) => {
            onChange('salesDealId', next?.id ?? '')
            onChange('salesDealLabel', next?.label ?? '')
            // 납품처는 거의 늘 딜의 고객사입니다. 채워 두고 다르면 고치게 합니다.
            if (row) {
              onChange('expectedCompanyId', row.customer_company_id)
              onChange('expectedCompanyLabel', row.customer_company_name)
            }
          }}
        />
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

      <Field label="요청부서" required error={errors.requestDepartment}>
        <input
          value={form.requestDepartment}
          disabled={disabled}
          maxLength={254}
          onChange={(e) => onChange('requestDepartment', e.target.value)}
        />
      </Field>

      <Field label="협조부서" required error={errors.cooperationDepartment}>
        <input
          value={form.cooperationDepartment}
          disabled={disabled}
          maxLength={254}
          onChange={(e) => onChange('cooperationDepartment', e.target.value)}
        />
      </Field>

      <Field label="납품예상 거래처" required error={errors.expectedCompanyId}>
        <RecordPicker<CustomerCompanyResponse>
          path="/customer-companies"
          label="납품예상 거래처"
          placeholder="회사 이름으로 검색"
          emptyText="일치하는 거래처가 없습니다."
          loadingText="거래처를 불러오는 중입니다."
          fallback="거래처를 불러오지 못했습니다."
          value={
            form.expectedCompanyId === ''
              ? null
              : { id: form.expectedCompanyId, label: form.expectedCompanyLabel }
          }
          disabled={disabled}
          invalid={errors.expectedCompanyId !== undefined}
          toOption={(row) => ({ id: row.id, label: row.name })}
          onChange={(next) => {
            onChange('expectedCompanyId', next?.id ?? '')
            onChange('expectedCompanyLabel', next?.label ?? '')
          }}
        />
      </Field>

      <Field label="작성자">
        {/* 서버가 로그인한 사람으로 채웁니다. 고를 수 있는 값이 아닙니다. */}
        <input value={createdBy} readOnly disabled aria-label="작성자" />
      </Field>

      {children}

      <div className={styles.isWide}>
        <ItemRows
          items={form.items}
          error={errors.items}
          rows={errors.itemRows}
          disabled={disabled}
          onChange={onItemsChange}
        />
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

/** 발주 화면 밖에서도 쓰던 이름이라 그대로 둡니다. 알맹이는 공용 FormField 입니다. */
export const Field = FormField
