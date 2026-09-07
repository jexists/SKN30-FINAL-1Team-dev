// 미팅의 실제 기록과 보고서에만 쓰는 참고자료를 목적별로 나눕니다.
import AttachmentPanel from '@/components/AttachmentPanel'
import { ChevronDownIcon, DocumentsIcon, EditIcon, PhoneIcon } from '@/components/icons'
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
          <h2>미팅 원문</h2>
          <span className={styles.required}>필수</span>
        </div>

        <details className={styles.sourceInput}>
          <summary>
            <PhoneIcon width={16} height={16} />
            <strong>STT · 녹음</strong>
            <span className={styles.inputStatus}>{audioSources.length}개</span>
            <ChevronDownIcon className={styles.caret} width={14} height={14} />
          </summary>
          <AttachmentPanel
            attachments={audioSources}
            readOnly={disabled}
            note=""
            acceptedKinds={['audio']}
            onAttach={(files, kinds) => onAttach(files, 'meeting_source', kinds)}
            onRemove={onRemoveAttachment}
            onExtractChange={onExtractChange}
          />
        </details>

        <details className={styles.sourceInput}>
          <summary>
            <DocumentsIcon width={16} height={16} />
            <strong>OCR · 이미지·PDF</strong>
            <span className={styles.inputStatus}>{documentSources.length}개</span>
            <ChevronDownIcon className={styles.caret} width={14} height={14} />
          </summary>
          <AttachmentPanel
            attachments={documentSources}
            readOnly={disabled}
            note=""
            acceptedKinds={['image', 'pdf']}
            onAttach={(files, kinds) => onAttach(files, 'meeting_source', kinds)}
            onRemove={onRemoveAttachment}
            onExtractChange={onExtractChange}
          />
        </details>

        <details className={styles.sourceInput}>
          <summary>
            <EditIcon width={16} height={16} />
            <strong>직접 입력</strong>
            <span className={styles.inputStatus}>{transcript.trim() ? '입력됨' : '내용 없음'}</span>
            <ChevronDownIcon className={styles.caret} width={14} height={14} />
          </summary>
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
        </details>
      </section>

      <details className={`${styles.block} ${styles.references}`}>
        <summary>
          <span className={styles.blockHead}>
            <span className={styles.blockTitle}>보고서 참고자료</span>
            <span className={styles.optional}>선택 · {references.length}개</span>
            <span className={styles.referenceAction}>첨부·보기</span>
          </span>
          <span className={styles.note}>배경자료로만 쓰며 미팅 발언으로 사용하지 않습니다.</span>
        </summary>
        <AttachmentPanel
          attachments={references}
          readOnly={disabled}
          note=""
          onAttach={(files) => onAttach(files, 'reference')}
          onRemove={onRemoveAttachment}
        />
      </details>

      {attachmentError && (
        <p className={styles.error} role="alert">
          {attachmentError}
        </p>
      )}
    </div>
  )
}
