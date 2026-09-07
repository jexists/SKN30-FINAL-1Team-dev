// 오른쪽 위. AI 에게 줄 것을 넣는 자리입니다.
//
// 넣는 것(첨부·미팅 내용)과 나오는 것(보고서)을 같은 열에 위아래로 두어, 누른 뒤
// 무엇이 달라지는지 눈이 옮겨 가지 않고도 보입니다. 왼쪽은 참고만 하는 열입니다.
import AttachmentPanel from '@/components/AttachmentPanel'
import Button from '@/components/Button'
import type { ReportAttachment } from '@/types'

import styles from './MeetingInputPanel.module.scss'

interface Props {
  attachments: ReportAttachment[]
  onAttach: (files: FileList | File[]) => void
  onRemoveAttachment: (id: string) => void
  /** 첨부를 받지 못했거나 음성 변환이 실패한 이유. */
  attachmentError: string | null
  transcript: string
  onTranscriptChange: (value: string) => void
  /** 'AI 보고서 작성' 을 누를 수 있는지. 미팅 내용이나 첨부가 있어야 누릅니다. */
  canGenerate: boolean
  generating: boolean
  /** 내용 칸의 이름. 업무보고(일일·주간·월간)는 미팅이 아니라 그 기간을 적습니다. */
  contentLabel?: string
  generateLabel?: string
  disabled: boolean
  onGenerate: () => void
}

export default function MeetingInputPanel({
  attachments,
  onAttach,
  onRemoveAttachment,
  attachmentError,
  transcript,
  onTranscriptChange,
  canGenerate,
  generating,
  contentLabel = '미팅 내용 (선택)',
  generateLabel = 'AI 보고서 작성',
  disabled,
  onGenerate,
}: Props) {
  return (
    <div className={styles.root}>
      <section className={styles.block}>
        <div className={styles.blockHead}>
          <h2>첨부 자료</h2>
        </div>

        <AttachmentPanel
          attachments={attachments}
          readOnly={disabled}
          note=""
          onAttach={onAttach}
          onRemove={onRemoveAttachment}
        />

        {attachmentError && (
          <p className={styles.error} role="alert">
            {attachmentError}
          </p>
        )}
      </section>

      <section className={styles.block}>
        <div className={styles.blockHead}>
          <h2>{contentLabel}</h2>
        </div>

        <label className="sr-only" htmlFor="transcript">
          {contentLabel} 직접 입력
        </label>
        <textarea
          id="transcript"
          className={styles.transcript}
          rows={8}
          value={transcript}
          disabled={disabled}
          placeholder="누구와 무엇을 이야기했는지 그대로 적으세요."
          onChange={(event) => onTranscriptChange(event.target.value)}
        />
      </section>

      <div className={styles.foot}>
        <Button
          type="button"
          className={styles.generate}
          onClick={onGenerate}
          disabled={disabled || !canGenerate || generating}
        >
          {generating ? `${generateLabel} 중…` : generateLabel}
        </Button>
      </div>
    </div>
  )
}
