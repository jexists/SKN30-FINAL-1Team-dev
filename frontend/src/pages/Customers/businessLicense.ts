import { isAxiosError } from 'axios'

import { client } from '@/api/client'
import { pollSummary } from '@/api/polling'
import { sizeLabel } from '@/utils/attachment'

/** 사업자등록증에서 읽어 고객사 등록 폼에 채울 값입니다. */
export interface BusinessLicenseDraft {
  company: string
  businessNo: string
  address: string
}

interface BusinessLicenseScanAccepted {
  scan_id: string
  processing_status: string
}

interface BusinessLicenseScanStatus {
  processing_status: string
  processing_error?: string | null
  fields?: {
    company: string
    business_no: string
    address: string
  } | null
}

/** 서버 한도와 맞춘 사업자등록증 업로드 한도입니다. */
export const MAX_BUSINESS_LICENSE_BYTES = 10 * 1024 * 1024
// 기존 호출부와의 호환성을 유지합니다.
export const MAX_PDF_BYTES = MAX_BUSINESS_LICENSE_BYTES

/** 사업자등록증 PDF와 사진을 모두 받습니다. */
export function businessLicenseProblem(file: File): string | null {
  const isPdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name)
  const isImage = file.type.startsWith('image/') || /\.(png|jpe?g|webp)$/i.test(file.name)
  if (!isPdf && !isImage) {
    return 'PDF 또는 이미지 파일만 올릴 수 있습니다. 사업자등록증을 골라 주세요.'
  }
  if (file.size > MAX_BUSINESS_LICENSE_BYTES) {
    return `파일이 ${sizeLabel(file.size)} 입니다. ${sizeLabel(MAX_BUSINESS_LICENSE_BYTES)} 까지 올릴 수 있습니다.`
  }
  if (file.size === 0) return '내용이 없는 파일입니다. 다른 파일을 골라 주세요.'
  return null
}

// 기존 이름을 사용하는 호출부도 PDF/이미지 검증을 동일하게 적용합니다.
export const pdfProblem = businessLicenseProblem

const UNAVAILABLE_SCAN_ERRORS = new Set([
  'ocr_unavailable',
  'ocr_not_configured',
  'llm_not_configured',
])

export class BusinessLicenseUnavailableError extends Error {
  constructor() {
    super('사업자등록증 인식 기능을 사용할 수 없습니다.')
    this.name = 'BusinessLicenseUnavailableError'
  }
}

export class BusinessLicenseScanError extends Error {
  readonly code: string

  constructor(code: string) {
    super(code)
    this.name = 'BusinessLicenseScanError'
    this.code = code
  }
}

/** PDF 또는 이미지를 서버 OCR로 보내고 완료될 때까지 결과를 조회합니다. */
export async function extractBusinessLicense(file: File): Promise<BusinessLicenseDraft> {
  const problem = businessLicenseProblem(file)
  if (problem !== null) throw new BusinessLicenseScanError('business_license_upload_invalid')

  try {
    const form = new FormData()
    form.append('file', file)
    let scanId = ''
    const scan = await pollSummary<BusinessLicenseScanStatus>({
      start: async () => {
        const accepted = await client.post<BusinessLicenseScanAccepted>(
          '/business-licenses/scan',
          form,
          { timeout: 120_000 },
        )
        scanId = accepted.data.scan_id
      },
      read: async () => {
        const response = await client.get<BusinessLicenseScanStatus>(
          `/business-licenses/scan/${scanId}`,
        )
        return response.data
      },
    })

    if (!scan.fields) throw new BusinessLicenseScanError('business_license_scan_empty')
    return {
      company: scan.fields.company,
      businessNo: scan.fields.business_no,
      address: scan.fields.address,
    }
  } catch (error: unknown) {
    if (isAxiosError(error) && [502, 503].includes(error.response?.status ?? 0)) {
      throw new BusinessLicenseUnavailableError()
    }
    if (error instanceof Error && UNAVAILABLE_SCAN_ERRORS.has(error.message)) {
      throw new BusinessLicenseUnavailableError()
    }
    if (isAxiosError(error) && error.code === 'ECONNABORTED') {
      throw new BusinessLicenseScanError('business_license_upload_timeout')
    }
    if (!isAxiosError(error) && error instanceof Error) {
      const code =
        error.message === 'document_summary_timeout'
          ? 'business_license_scan_timeout'
          : error.message
      throw new BusinessLicenseScanError(code)
    }
    throw error
  }
}
