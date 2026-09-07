import type { ReportAttachment, ReportAttachmentPayload } from '@/types'

export function sizeLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
}

/** 업로드가 끝난 첨부만 AgentRun의 일회용 생성 입력으로 보냅니다. */
export function attachmentPayloadsOf(attachments: ReportAttachment[]): ReportAttachmentPayload[] {
  return attachments.flatMap((attachment) =>
    attachment.state === 'done' && attachment.extract
      ? [
          {
            id: attachment.id,
            kind: attachment.kind,
            name: attachment.name,
            byte_size: attachment.byteSize,
            extract: attachment.extract,
          },
        ]
      : [],
  )
}

export function attachmentsFromPayload(payloads: ReportAttachmentPayload[]): ReportAttachment[] {
  return payloads.map((attachment) => ({
    id: attachment.id,
    kind: attachment.kind,
    name: attachment.name,
    byteSize: attachment.byte_size,
    state: 'done',
    extract: attachment.extract,
  }))
}
