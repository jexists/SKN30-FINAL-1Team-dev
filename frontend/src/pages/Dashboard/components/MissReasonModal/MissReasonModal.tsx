// 지시사항을 미이행으로 남기며 까닭을 적는 자리.
//
// 사유를 필수로 둡니다. 표시만 바뀌고 왜 못 했는지가 없으면 팀장이 결국 다시 물어야 하고,
// 그러면 이 화면이 있으나 마나 합니다. 서버도 같은 조건으로 거절합니다.
import { useState } from 'react'

import Button from '@/components/Button'
import FormField from '@/components/FormField'
import Modal from '@/components/Modal'

import styles from './MissReasonModal.module.scss'

interface Props {
  busy: boolean
  onCancel: () => void
  onSubmit: (reason: string) => void
}

export default function MissReasonModal({ busy, onCancel, onSubmit }: Props) {
  const [reason, setReason] = useState('')
  // 낸 적이 있는가. 포커스가 떠난 것만으로 빨간 글씨를 세우지 않습니다. 드로어와 모달이
  // 겹쳐 열리면서 포커스가 한 번 오갈 때가 있어, 아직 아무것도 하지 않은 사람에게 오류가
  // 먼저 보이는 일이 생깁니다.
  const [submitted, setSubmitted] = useState(false)

  const trimmed = reason.trim()
  const invalid = submitted && trimmed === ''

  return (
    <Modal
      title="업무 미이행"
      description="적어 둔 사유는 팀장이 공지관리 화면에서 봅니다."
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
          <Button type="submit" disabled={busy}>
            {busy ? '저장 중…' : '저장'}
          </Button>
        </>
      }
    >
      <FormField
        label="미이행 사유"
        required
        error={invalid ? '미이행 사유를 적어 주세요.' : undefined}
      >
        <textarea
          className={styles.textarea}
          value={reason}
          rows={4}
          maxLength={1000}
          placeholder="예) 거래처 일정 변경으로 방문하지 못함"
          onChange={(event) => setReason(event.target.value)}
        />
      </FormField>
    </Modal>
  )
}
