// 미팅의 실제 기록과 보고서에만 쓰는 참고자료를 목적별로 나눕니다.
// 셋 다 펼친 채로 둡니다 — 무엇을 넣어야 하는지가 여닫이 뒤에 숨지 않습니다.
import AttachmentPanel from '@/components/AttachmentPanel'
import { DocumentsIcon, EditIcon, InfoIcon, PhoneIcon } from '@/components/icons'
import type { AttachmentKind, AttachmentPurpose, ReportAttachment } from '@/types'
import { meetingAttachmentPurposeOf } from '@/utils/attachment'

import styles from './MeetingInputPanel.module.scss'

interface Props {
  attachments: ReportAttachment[]
  onAttach: (
    files: FileList | File[],
    purpose: AttachmentPurpose,
    acceptedKinds?: readonly AttachmentKind[],
  ) => void
  onRemoveAttachment: (id: string) => void
  onExtractChange: (id: string, extract: string) => void
  /** 첨부를 받지 못했거나 음성 변환이 실패한 이유. */
  attachmentError: string | null
  transcript: string
  onTranscriptChange: (value: string) => void
  disabled: boolean
}

/**
 * 무엇을 넣는 자리인지에 대한 설명. 본문처럼 깔아 두면 정작 넣을 것을 밀어내서
 * 물어볼 때만 나오게 둡니다. 여닫는 상태는 두지 않고 hover·포커스로만 폅니다.
 */
function InfoHint({ text }: { text: string }) {
  return (
    <span className={styles.hint}>
      <button type="button" className={styles.hintBtn} aria-label={text}>
        <InfoIcon width={14} height={14} />
      </button>
      <span className={styles.tip} role="tooltip">
        {text}
      </span>
    </span>
  )
}

export default function MeetingInputPanel({
  attachments,
  onAttach,
  onRemoveAttachment,
  onExtractChange,
  attachmentError,
  transcript,
  onTranscriptChange,
  disabled,
}: Props) {
  const sourceAttachments = attachments.filter(
    (item) => meetingAttachmentPurposeOf(item) === 'meeting_source',
  )
  const references = attachments.filter((item) => meetingAttachmentPurposeOf(item) === 'reference')
  const audioSources = sourceAttachments.filter((item) => item.kind === 'audio')
  const documentSources = sourceAttachments.filter((item) => item.kind !== 'audio')

  return (
    <div className={styles.root}>
      <section className={styles.block}>
        <div className={styles.blockHead}>
          <h2>
            미팅 원문
            <span className={styles.required} aria-hidden="true">
              *
            </span>
            <span className="sr-only">필수</span>
          </h2>
          <InfoHint text="보고서의 근거가 되는 원본 기록입니다. 녹음·이미지·PDF·직접 입력 중 하나만 넣어도 됩니다." />
        </div>

        <div className={styles.sources}>
          <div className={styles.source}>
            <div className={styles.sourceHead}>
              <PhoneIcon width={16} height={16} />
              <strong>녹음</strong>
              <span className={styles.inputStatus}>{audioSources.length}개</span>
            </div>
            <AttachmentPanel
              attachments={audioSources}
              readOnly={disabled}
              note=""
              acceptedKinds={['audio']}
              onAttach={(files, kinds) => onAttach(files, 'meeting_source', kinds)}
              onRemove={onRemoveAttachment}
              onExtractChange={onExtractChange}
            />
          </div>

          <div className={styles.source}>
            <div className={styles.sourceHead}>
              <DocumentsIcon width={16} height={16} />
              <strong>이미지·PDF</strong>
              <span className={styles.inputStatus}>{documentSources.length}개</span>
            </div>
            <AttachmentPanel
              attachments={documentSources}
              readOnly={disabled}
              note=""
              acceptedKinds={['image', 'pdf']}
              onAttach={(files, kinds) => onAttach(files, 'meeting_source', kinds)}
              onRemove={onRemoveAttachment}
              onExtractChange={onExtractChange}
            />
          </div>

          <div className={`${styles.source} ${styles.wide}`}>
            <div className={styles.sourceHead}>
              <EditIcon width={16} height={16} />
              <strong>직접 입력</strong>
              <span className={styles.inputStatus}>
                {transcript.trim() ? '입력됨' : '내용 없음'}
              </span>
            </div>
            <label className="sr-only" htmlFor="transcript">
              직접 입력
            </label>
            <textarea
              id="transcript"
              className={styles.transcript}
              rows={5}
              value={transcript}
              disabled={disabled}
              placeholder="직접 기록한 미팅 내용을 추가하세요."
              onChange={(event) => onTranscriptChange(event.target.value)}
            />
          </div>
        </div>

        {attachmentError && (
          <p className={styles.error} role="alert">
            {attachmentError}
          </p>
        )}
      </section>

      <section className={styles.block}>
        <div className={styles.blockHead}>
          <h2>보고서 참고자료</h2>
          <InfoHint text="선택 입력입니다. 배경자료로만 쓰며 미팅 발언으로 사용하지 않습니다." />
        </div>
        <AttachmentPanel
          attachments={references}
          readOnly={disabled}
          note=""
          onAttach={(files) => onAttach(files, 'reference')}
          onRemove={onRemoveAttachment}
        />
      </section>
    </div>
  )
}
