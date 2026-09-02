import { isAxiosError } from 'axios'

import { client } from '@/api/client'
import { pollSummary } from '@/api/polling'
import { downscaleImage } from '@/utils/image'

/** 명함에서 읽어 낸 값. 고객 등록 폼의 칸과 이름을 맞춰 둡니다. */
export interface BusinessCardDraft {
  org: string
  name: string
  dept: string
  title: string
  email: string
  phone: string
  matches: BusinessCardMatch[]
  sourceImage: File
}

export interface BusinessCardMatch {
  contact_id: string
  company_id: string
  company_name: string
  name: string
  phone: string
  email: string | null
  matched_by: string[]
}

interface BusinessCardScanAccepted {
  scan_id: string
  processing_status: string
}

interface BusinessCardScanStatus {
  processing_status: string
  processing_error?: string | null
  fields?: {
    name: string
    company_name: string
    department: string
    job_title: string
    email: string
    phone: string
  } | null
}

/** 서버가 processing_error로 돌려주는, 인식 기능 자체를 쓸 수 없는 상태입니다. */
const UNAVAILABLE_SCAN_ERRORS = new Set([
  'ocr_unavailable',
  'ocr_not_configured',
  'llm_not_configured',
])

export class BusinessCardUnavailableError extends Error {
  constructor() {
    super('명함 인식이 아직 연결되지 않았습니다.')
    this.name = 'BusinessCardUnavailableError'
  }
}

/**
 * 실패한 단계를 코드로 남깁니다.
 *
 * 화면이 모든 실패를 "사진이 흐린가 봅니다" 로 뭉뚱그리면, 업로드가 끊긴 경우에도
 * 사용자가 사진만 다시 찍게 됩니다. errorMessage 가 이 코드를 문구로 바꿉니다.
 */
export class BusinessCardScanError extends Error {
  readonly code: string

  constructor(code: string) {
    super(code)
    this.name = 'BusinessCardScanError'
    this.code = code
  }
}

/** 인식 한 건이 지나는 단계. 화면은 이걸 그대로 진행 표시로 씁니다. */
export type ScanProgress =
  | { phase: 'resizing' }
  | { phase: 'uploading'; percent: number }
  | { phase: 'recognizing'; elapsedSeconds: number }

/**
 * 서버 워커가 긴 변 2400px 로 줄여 인식하므로(BUSINESS_CARD_MAX_SIDE), 그보다 큰
 * 원본을 그대로 올려도 인식 결과는 같습니다. 같은 값으로 미리 줄여 보냅니다.
 */
const UPLOAD_MAX_SIDE = 2400

/** 명함 이미지 한 장을 읽어 기존 고객 등록 폼의 필드로 바꿉니다. */
export async function recognizeBusinessCard(
  image: File,
  onProgress?: (progress: ScanProgress) => void,
): Promise<BusinessCardDraft> {
  try {
    onProgress?.({ phase: 'resizing' })
    const upload = await downscaleImage(image, UPLOAD_MAX_SIDE)
    const form = new FormData()
    form.append('image', upload)

    // OCR과 구조화 LLM을 한 요청에서 기다리면 CloudFront origin timeout을 넘겨
    // 504가 됩니다. 서버는 202로 접수만 하고, 결과는 자료요약과 같은 방식으로
    // 폴링해서 받습니다.
    let scanId = ''
    const startedAt = Date.now()
    const scan = await pollSummary<BusinessCardScanStatus>({
      start: async () => {
        // 이 요청은 이제 업로드와 검증까지만 담당합니다. 축소해도 느린 회선에서는
        // 기본 10초 제한에 걸릴 수 있어 따로 넉넉히 둡니다.
        const accepted = await client.post<BusinessCardScanAccepted>('/business-cards/scan', form, {
          timeout: 120_000,
          onUploadProgress: (event) => {
            if (!event.total) return
            onProgress?.({ phase: 'uploading', percent: (event.loaded / event.total) * 100 })
          },
        })
        scanId = accepted.data.scan_id
      },
      read: async () => {
        onProgress?.({
          phase: 'recognizing',
          elapsedSeconds: Math.round((Date.now() - startedAt) / 1000),
        })
        const status = await client.get<BusinessCardScanStatus>(`/business-cards/scan/${scanId}`)
        return status.data
      },
    })
    if (!scan.fields) {
      throw new BusinessCardScanError('business_card_scan_empty')
    }
    const fields = {
      name: scan.fields.name,
      company_name: scan.fields.company_name,
      department: scan.fields.department,
      job_title: scan.fields.job_title,
      email: scan.fields.email,
      phone: scan.fields.phone,
    }
    let matches: BusinessCardMatch[] = []
    try {
      const response = await client.post<BusinessCardMatch[]>('/business-cards/matches', fields)
      matches = response.data
    } catch {
      // 중복 후보 조회는 보조 기능이므로 인식 결과 자체를 막지 않습니다.
    }
    return {
      org: fields.company_name,
      name: fields.name,
      dept: fields.department,
      title: fields.job_title,
      email: fields.email,
      phone: fields.phone,
      matches,
      sourceImage: image,
    }
  } catch (error: unknown) {
    // 접수 자체가 막힌 경우와, 폴링이 실패 코드를 받은 경우를 같은 문구로 안내합니다.
    if (isAxiosError(error) && [502, 503].includes(error.response?.status ?? 0)) {
      throw new BusinessCardUnavailableError()
    }
    if (error instanceof Error && UNAVAILABLE_SCAN_ERRORS.has(error.message)) {
      throw new BusinessCardUnavailableError()
    }
    // 업로드가 제한시간을 넘긴 경우입니다. 사진 문제로 안내하면 안 됩니다.
    if (isAxiosError(error) && error.code === 'ECONNABORTED') {
      throw new BusinessCardScanError('business_card_upload_timeout')
    }
    // 폴링은 실패 코드와 시간초과를 문자열로 올립니다. 코드가 실린 오류로 감쌉니다.
    if (!isAxiosError(error) && error instanceof Error) {
      // 폴링 유틸이 자료요약과 공유되어 시간초과 코드가 문서 쪽 이름으로 옵니다.
      const code =
        error.message === 'document_summary_timeout' ? 'business_card_scan_timeout' : error.message
      throw new BusinessCardScanError(code)
    }
    throw error
  }
}

/** 명함 한 장이면 충분한 크기입니다. 더 큰 사진은 인식이 아니라 전송에서 막힙니다. */
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024
