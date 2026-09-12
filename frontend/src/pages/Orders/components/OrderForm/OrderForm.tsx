// 발주 작성·수정 모달입니다. 항목은 OrderFields 가, 검사는 orderForm 이 갖고
// 여기서는 모달 껍데기와 제출만 다룹니다.
//
// 딜 상세에서 단계를 발주로 옮길 때도 이 모달로 새 발주를 냅니다. 그때는 어느 딜인지
// 이미 정해져 있어 `deal` 로 받고 딜 고르개를 잠급니다.
import { useEffect, useRef, useState } from 'react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import type { SalesDeal } from '@/pages/Deals/useSalesDeals'
import type { ApiPurchaseOrder, PurchaseOrderStatusResponse } from '@/types'

import {
  initialState,
  toDraft,
  validate,
  type FormErrors,
  type FormState,
  type ItemState,
} from '../../orderForm'
import type { OrderDraft } from '../../useOrderList'
import OrderFields from '../OrderFields'

interface Props {
  /** 고칠 발주. 주지 않으면 새 발주를 냅니다. */
  order?: ApiPurchaseOrder
  /** 새 발주를 낼 딜. 주면 딜과 납품처를 채운 채로 열고 딜은 못 바꿉니다. */
  deal?: SalesDeal
  /** 작성자. 새 발주는 지금 로그인한 사람입니다. */
  createdBy?: string
  statuses: PurchaseOrderStatusResponse[]
  suppliers: string[]
  optionsLoading?: boolean
  onClose: () => void
  onSubmit: (draft: OrderDraft) => Promise<void>
}

export default function OrderForm({
  order,
  deal,
  createdBy,
  statuses,
  suppliers,
  optionsLoading = false,
  onClose,
  onSubmit,
}: Props) {
  const [form, setForm] = useState<FormState>(() => {
    const base = initialState(order)
    if (order !== undefined || deal === undefined) return base
    // 납품처는 거의 늘 딜의 고객사입니다. OrderFields 의 딜 고르개와 같은 값을 채웁니다.
    return {
      ...base,
      salesDealId: deal.id,
      salesDealLabel: deal.no,
      expectedCompanyId: deal.customerCompanyId,
      expectedCompanyLabel: deal.org,
    }
  })
  const [errors, setErrors] = useState<FormErrors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const submittingRef = useRef(false)

  // 상태 목록은 늦게 옵니다. 새 발주는 오는 대로 첫 상태를 채웁니다.
  useEffect(() => {
    if (form.stageCode !== '' || statuses.length === 0) return
    setForm((current) => ({ ...current, stageCode: statuses[0].code }))
  }, [form.stageCode, statuses])

  const set = (key: Exclude<keyof FormState, 'items'>, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const setItems = (items: ItemState[]) => setForm((prev) => ({ ...prev, items }))

  const close = () => {
    if (!submittingRef.current) onClose()
  }

  const submit = async () => {
    if (submittingRef.current) return
    const found = validate(form)
    setErrors(found)
    if (Object.keys(found).length > 0) return

    submittingRef.current = true
    setSubmitting(true)
    setSubmitError(null)
    try {
      await onSubmit(toDraft(form))
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '발주를 저장하지 못했습니다.')
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title={order ? '발주 수정' : '발주 추가'}
      description={
        order
          ? `${order.no} · 발주번호와 상태는 여기서 바꾸지 않습니다.`
          : `${deal?.no ?? ''} · 발주번호는 저장할 때 자동으로 매깁니다.`
      }
      onClose={close}
      onSubmit={() => void submit()}
      footer={
        <>
          <Button type="button" variant="outline" disabled={submitting} onClick={close}>
            취소
          </Button>
          <Button type="submit" disabled={submitting || optionsLoading || statuses.length === 0}>
            {submitting ? '저장 중…' : '저장'}
          </Button>
        </>
      }
    >
      <OrderFields
        form={form}
        errors={errors}
        statuses={statuses}
        suppliers={suppliers}
        optionsLoading={optionsLoading}
        disabled={submitting}
        // 발주번호와 상태는 수정에서 바꾸지 않습니다. 새 발주는 상태를 골라야 합니다.
        showStatus={order === undefined}
        lockSalesDeal
        createdBy={order?.createdBy ?? createdBy ?? ''}
        onChange={set}
        onItemsChange={setItems}
      />
      {submitError && <p role="alert">{submitError}</p>}
    </Modal>
  )
}
