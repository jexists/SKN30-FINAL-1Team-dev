import type { ReportAttachmentPayload } from '@/types'

import { client } from './client'

const UPLOAD_TIMEOUT_MS = 300_000

export async function uploadReportAttachment(file: File): Promise<ReportAttachmentPayload> {
  const form = new FormData()
  form.append('upload', file)
  return (
    await client.post<ReportAttachmentPayload>('/report-attachments', form, {
      timeout: UPLOAD_TIMEOUT_MS,
    })
  ).data
}
