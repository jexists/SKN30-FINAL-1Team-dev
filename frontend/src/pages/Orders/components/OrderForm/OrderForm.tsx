// 발주 수정 모달입니다. 항목은 OrderFields 가, 검사는 orderForm 이 갖고
// 여기서는 모달 껍데기와 제출만 다룹니다.
import { useState } from 'react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import type { PurchaseOrder } from '@/types'

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
  order: PurchaseOrder
  onClose: () => void
  onSubmit: (draft: OrderDraft) => void
}

export default function OrderForm({ order, onClose, onSubmit }: Props) {
  const [form, setForm] = useState<FormState>(() => initialState(order))
  const [errors, setErrors] = useState<FormErrors>({})

  const set = (key: Exclude<keyof FormState, 'items'>, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const setItems = (items: ItemState[]) => setForm((prev) => ({ ...prev, items }))

  const submit = () => {
    const found = validate(form)
    setErrors(found)
    if (Object.keys(found).length > 0) return
    onSubmit(toDraft(form))
  }

  return (
    <Modal
      title="발주 수정"
      description={`${order.no} · 발주번호는 바꾸지 않습니다.`}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button type="submit">저장</Button>
        </>
      }
    >
      <OrderFields form={form} errors={errors} onChange={set} onItemsChange={setItems} />
    </Modal>
  )
}
