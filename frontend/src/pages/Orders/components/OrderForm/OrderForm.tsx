// 발주 수정 모달입니다. 항목은 OrderFields 가, 검사는 orderForm 이 갖고
// 여기서는 모달 껍데기와 제출만 다룹니다.
import { useRef, useState } from 'react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
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
  order: ApiPurchaseOrder
  statuses: PurchaseOrderStatusResponse[]
  suppliers: string[]
  optionsLoading?: boolean
  onClose: () => void
  onSubmit: (draft: OrderDraft) => Promise<void>
}

export default function OrderForm({
  order,
  statuses,
  suppliers,
  optionsLoading = false,
  onClose,
  onSubmit,
}: Props) {
  const [form, setForm] = useState<FormState>(() => initialState(order))
  const [errors, setErrors] = useState<FormErrors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const submittingRef = useRef(false)

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
      title="발주 수정"
      description={`${order.no} · 발주번호와 상태는 여기서 바꾸지 않습니다.`}
      onClose={close}
      onSubmit={() => void submit()}
      footer={
        <>
          <Button type="button" variant="outline" disabled={submitting} onClick={close}>
            취소
          </Button>
          <Button type="submit" disabled={submitting || optionsLoading}>
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
        showStatus={false}
        lockSalesDeal
        createdBy={order.createdBy}
        onChange={set}
        onItemsChange={setItems}
      />
      {submitError && <p role="alert">{submitError}</p>}
    </Modal>
  )
}
