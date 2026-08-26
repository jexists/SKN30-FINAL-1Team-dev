import { isAxiosError } from 'axios'

import { client } from '@/api/client'

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

interface BusinessCardScanResponse {
  fields: {
    name: string
    company_name: string
    department: string
    job_title: string
    email: string
    phone: string
  }
}

export class BusinessCardUnavailableError extends Error {
  constructor() {
    super('명함 인식이 아직 연결되지 않았습니다.')
    this.name = 'BusinessCardUnavailableError'
  }
}

/** 명함 이미지 한 장을 읽어 기존 고객 등록 폼의 필드로 바꿉니다. */
export async function recognizeBusinessCard(image: File): Promise<BusinessCardDraft> {
  const form = new FormData()
  form.append('image', image)
  try {
    const { data } = await client.post<BusinessCardScanResponse>('/business-cards/scan', form)
    const fields = {
      name: data.fields.name,
      company_name: data.fields.company_name,
      department: data.fields.department,
      job_title: data.fields.job_title,
      email: data.fields.email,
      phone: data.fields.phone,
    }
    let matches: BusinessCardMatch[] = []
    try {
      const response = await client.post<BusinessCardMatch[]>('/business-cards/matches', fields)
      matches = response.data
    } catch {
      // 중복 후보 조회는 보조 기능이므로 인식 결과 자체를 막지 않습니다.
    }
    return {
      org: data.fields.company_name,
      name: data.fields.name,
      dept: data.fields.department,
      title: data.fields.job_title,
      email: data.fields.email,
      phone: data.fields.phone,
      matches,
      sourceImage: image,
    }
  } catch (error: unknown) {
    if (isAxiosError(error) && [502, 503].includes(error.response?.status ?? 0)) {
      throw new BusinessCardUnavailableError()
    }
    throw error
  }
}

/** 명함 한 장이면 충분한 크기입니다. 더 큰 사진은 인식이 아니라 전송에서 막힙니다. */
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024
