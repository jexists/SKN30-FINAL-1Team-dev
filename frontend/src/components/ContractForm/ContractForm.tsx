// 계약 추가·수정 모달입니다. 항목은 ContractFields 가, 검사는 contractForm 이 갖고
// 여기서는 모달 껍데기와 제출만 다룹니다.
// contract 를 주면 수정, 주지 않으면 추가입니다.
import { useState } from 'react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'

import ContractFields from '@/components/ContractFields'
import type { Contract, ContractDraft } from '@/types'

import { initialState, toDraft, validate, type FormErrors, type FormState } from './form'

interface Props {
  /** 수정할 계약. 없으면 새로 만듭니다. */
  contract?: Contract
  /** 추가할 단계 이름. 새로 만들 때 어디에 들어가는지 알려 줍니다. */
  stageName?: string
  onClose: () => void
  onSubmit: (draft: ContractDraft) => void
}

export default function ContractForm({ contract, stageName, onClose, onSubmit }: Props) {
  const [form, setForm] = useState<FormState>(() => initialState(contract))
  const [errors, setErrors] = useState<FormErrors>({})

  const set = (key: keyof FormState, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const submit = () => {
    const found = validate(form)
    setErrors(found)
    if (Object.keys(found).length > 0) return
    onSubmit(toDraft(form))
  }

  const editing = contract !== undefined

  return (
    <Modal
      title={editing ? '계약 수정' : '계약 추가'}
      description={
        editing
          ? `${contract.no} · 단계는 보드에서 카드를 옮겨 바꿉니다.`
          : `${stageName ?? ''} 단계 맨 위에 추가됩니다. 계약번호는 자동으로 매깁니다.`
      }
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button type="submit">{editing ? '저장' : '계약 추가'}</Button>
        </>
      }
    >
      <ContractFields form={form} errors={errors} onChange={set} />
    </Modal>
  )
}
