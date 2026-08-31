// 보고서를 반려하며 까닭을 적는 자리.
//
// 사유를 필수로 둡니다. 무엇을 고쳐야 하는지 없이 돌려보내면 팀원이 같은 것을 그대로 다시
// 냅니다. 서버도 같은 조건으로 거절하므로 여기서 먼저 막아 왕복을 줄입니다.
import { useState } from 'react'

import Button from '@/components/Button'
import FormField from '@/components/FormField'
import Modal from '@/components/Modal'

import styles from './RejectReasonModal.module.scss'

interface Props {
  busy: boolean
  onCancel: () => void
  onSubmit: (reason: string) => void
}

export default function RejectReasonModal({ busy, onCancel, onSubmit }: Props) {
  const [reason, setReason] = useState('')
  // 낸 적이 있는가. 포커스가 떠난 것만으로 빨간 글씨를 세우지 않습니다. 드로어와 모달이
  // 겹쳐 열리면서 포커스가 한 번 오갈 때가 있어, 아직 아무것도 하지 않은 사람에게 오류가
  // 먼저 보이는 일이 생깁니다.
  const [submitted, setSubmitted] = useState(false)

  const trimmed = reason.trim()
  const invalid = submitted && trimmed === ''

  return (
    <Modal
      title="보고서 반려"
      description="반려한 보고서는 담당 팀원이 다시 고쳐 낼 수 있습니다."
      onClose={onCancel}
      onSubmit={() => {
        setSubmitted(true)
        if (trimmed === '') return
        onSubmit(trimmed)
      }}
      footer={
        <>
          <Button type="button" variant="outline" disabled={busy} onClick={onCancel}>
            취소
          </Button>
          <Button type="submit" variant="outline" className={styles.danger} disabled={busy}>
            {busy ? '처리 중…' : '반려 처리'}
          </Button>
        </>
      }
    >
      <FormField label="반려 사유" required error={invalid ? '반려 사유를 적어 주세요.' : undefined}>
        <textarea
          className={styles.textarea}
          value={reason}
          rows={4}
          maxLength={5000}
          placeholder="예) 고객 요구사항 내용이 부족합니다."
          onChange={(event) => setReason(event.target.value)}
        />
      </FormField>
    </Modal>
  )
}
