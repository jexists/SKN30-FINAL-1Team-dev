// 미팅의 실제 기록과 보고서에만 쓰는 참고자료를 목적별로 나눕니다.
// 셋 다 펼친 채로 둡니다 — 무엇을 넣어야 하는지가 여닫이 뒤에 숨지 않습니다.
import AttachmentPanel from '@/components/AttachmentPanel'
import { DocumentsIcon, EditIcon, PhoneIcon } from '@/components/icons'
import type { AttachmentKind, AttachmentPurpose, ReportAttachment } from '@/types'
import { meetingAttachmentPurposeOf } from '@/utils/attachment'

import styles from './MeetingInputPanel.module.scss'

interface Props {
  attachments: ReportAttachment[]
  /** 저장된 보고서를 다시 여는 화면. 서버에 있는 원본을 받아 와야 얼굴이 보입니다. */
  reportId?: string
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
  reportId,
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
          <h3>
            미팅 원문
            <span className={styles.required} aria-hidden="true">
              *
            </span>
            <span className="sr-only">필수</span>
          </h3>
        </div>
        {/* 물어봐야 나오는 설명은 결국 아무도 안 읽어서, 제목 아래에 회색으로 그냥 깔아 둡니다. */}
        <p className={styles.hint}>
          보고서의 근거가 되는 원본 기록입니다. 녹음·이미지·PDF·직접 입력 중 하나만 넣어도 됩니다.
        </p>

        <div className={styles.sources}>
          <AttachmentPanel
            attachments={audioSources}
            reportId={reportId}
            readOnly={disabled}
            note=""
            title="녹음"
            icon={<PhoneIcon width={18} height={18} />}
            description="음성 파일을 업로드하면 자동으로 STT가 변환되어 원문을 확인할 수 있습니다."
            hint="MP3, M4A, WAV 등"
            acceptedKinds={['audio']}
            onAttach={(files, kinds) => onAttach(files, 'meeting_source', kinds)}
            onRemove={onRemoveAttachment}
            onExtractChange={onExtractChange}
          />

          <AttachmentPanel
            attachments={documentSources}
            reportId={reportId}
            readOnly={disabled}
            note=""
            title="이미지·PDF"
            icon={<DocumentsIcon width={18} height={18} />}
            description="회의 자료, 사진, PDF 파일을 업로드할 수 있습니다."
            hint="JPG, PNG, PDF 등"
            acceptedKinds={['image', 'pdf']}
            onAttach={(files, kinds) => onAttach(files, 'meeting_source', kinds)}
            onRemove={onRemoveAttachment}
            onExtractChange={onExtractChange}
          />

          <div className={styles.source}>
            <div className={styles.sourceHead}>
              <EditIcon width={18} height={18} />
              <strong>직접 입력</strong>
            </div>
            <p className={styles.description}>
              녹음이나 파일 외에 직접 메모한 미팅 내용을 입력할 수 있습니다.
            </p>
            <label className="sr-only" htmlFor="transcript">
              직접 입력
            </label>
            <textarea
              id="transcript"
              className={styles.transcript}
              rows={5}
              value={transcript}
              /* 잠겨도 이미 쓴 내용은 작성 화면과 같은 대비로 읽혀야 합니다. disabled 는 글씨까지 흐립니다. */
              readOnly={disabled}
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
        {/* 머리는 원문 쪽 갈래들과 같이 AttachmentPanel 이 냅니다 — 사진이 들어오면 우측에 추가 버튼. */}
        <AttachmentPanel
          attachments={references}
          reportId={reportId}
          readOnly={disabled}
          note=""
          gallery
          title="보고서 참고자료"
          icon={<DocumentsIcon width={18} height={18} />}
          description="선택 입력입니다. 배경자료로만 쓰며 미팅 발언으로 사용하지 않습니다."
          hint="JPG, PNG 등"
          acceptedKinds={['image']}
          onAttach={(files, kinds) => onAttach(files, 'reference', kinds)}
          onRemove={onRemoveAttachment}
        />
      </section>
    </div>
  )
}
