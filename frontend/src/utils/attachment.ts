import type { ReportAttachment, ReportAttachmentPayload } from '@/types'

/** 목적 필드가 없던 미팅 실행은 기존 음성 원문·문서 참고 구분을 유지합니다. */
export function meetingAttachmentPurposeOf(attachment: Pick<ReportAttachment, 'kind' | 'purpose'>) {
  return attachment.purpose ?? (attachment.kind === 'audio' ? 'meeting_source' : 'reference')
}

export function sizeLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
}

/** 업로드가 끝난 첨부와 원본 보관 표시를 생성 입력·제출본에 보존합니다. */
export function attachmentPayloadsOf(attachments: ReportAttachment[]): ReportAttachmentPayload[] {
  return attachments.flatMap((attachment) =>
    attachment.state === 'done' && (attachment.extract || attachment.originalStored)
      ? [
          {
            id: attachment.id,
            kind: attachment.kind,
            ...(attachment.purpose ? { purpose: attachment.purpose } : {}),
            name: attachment.name,
            byte_size: attachment.byteSize,
            extract: attachment.extract ?? '',
            ...(attachment.originalStored ? { original_stored: attachment.originalStored } : {}),
          },
        ]
      : [],
  )
}

export function attachmentsFromPayload(payloads: ReportAttachmentPayload[]): ReportAttachment[] {
  return payloads.map((attachment) => ({
    id: attachment.id,
    kind: attachment.kind,
    ...(attachment.purpose ? { purpose: attachment.purpose } : {}),
    name: attachment.name,
    byteSize: attachment.byte_size,
    state: 'done',
    extract: attachment.extract,
    ...(attachment.original_stored ? { originalStored: attachment.original_stored } : {}),
  }))
}
