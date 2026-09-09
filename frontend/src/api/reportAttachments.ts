import { isAxiosError } from 'axios'

import type { ReportAttachmentPayload } from '@/types'

import { client } from './client'

const UPLOAD_TIMEOUT_MS = 300_000

export async function reportAttachmentLimits(): Promise<{
  audio_max_bytes: number
  document_max_bytes: number
}> {
  return (await client.get('/report-attachments/limits')).data
}

export async function uploadReportAttachment(file: File): Promise<ReportAttachmentPayload> {
  const form = new FormData()
  form.append('upload', file)
  return (
    await client.post<ReportAttachmentPayload>('/report-attachments', form, {
      timeout: UPLOAD_TIMEOUT_MS,
    })
  ).data
}

/** 보고서 조회 권한을 확인한 서버에서 원본 바이트를 받습니다. */
export async function downloadReportAttachment(
  reportId: string,
  attachmentId: string,
  signal?: AbortSignal,
): Promise<Blob> {
  try {
    return (
      await client.get<Blob>(`/reports/${reportId}/attachments/${attachmentId}/download`, {
        responseType: 'blob',
        timeout: UPLOAD_TIMEOUT_MS,
        signal,
      })
    ).data
  } catch (reason: unknown) {
    // blob 요청의 업무 오류도 기존 코드→문구 변환을 사용할 수 있게 읽습니다.
    if (isAxiosError(reason) && reason.response?.data instanceof Blob) {
      try {
        reason.response.data = JSON.parse(await reason.response.data.text())
      } catch {
        // JSON이 아닌 응답은 상태 코드와 기본 오류 문구로 처리합니다.
      }
    }
    throw reason
  }
}
