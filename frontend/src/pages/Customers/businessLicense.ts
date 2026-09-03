// 사업자등록증(PDF)으로 고객을 넣는 길의 화면 밖 부분입니다.
//
// 읽어 낸 값은 명함과 같은 방식으로 고객 등록 폼에 그대로 채워집니다.
// 아직 읽어 주는 서버가 없습니다. 그래서 화면은 extractBusinessLicense 의 Promise 만
// 보게 두고, 실제 OCR 이 붙을 때 이 파일 한 곳만 고치면 되도록 갈라 둡니다.
import { sizeLabel } from '@/utils/attachment'

/** 명함(10MB)과 같은 한도입니다. 사업자등록증 한 장은 이보다 훨씬 작습니다. */
export const MAX_PDF_BYTES = 10 * 1024 * 1024

/** 사업자등록증에서 읽어 낼 값들. 등록 폼의 회사 칸에 그대로 들어갑니다. */
export interface BusinessLicenseDraft {
  /** 상호(법인명) */
  company: string
  /** 등록번호. 화면에서는 123-45-67890 모양으로 적습니다. */
  businessNo: string
  /** 사업장 소재지 */
  address: string
}

export const EMPTY_DRAFT: BusinessLicenseDraft = {
  company: '',
  businessNo: '',
  address: '',
}

/**
 * 올린 파일의 문제. 없으면 null 입니다.
 *
 * 브라우저가 확장자만 보고 type 을 비워 보내는 경우가 있어 둘 중 하나만 맞아도 PDF 로 봅니다.
 */
export function pdfProblem(file: File): string | null {
  const isPdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name)
  if (!isPdf) return 'PDF 파일만 올릴 수 있습니다. 사업자등록증 PDF를 골라 주세요.'
  if (file.size > MAX_PDF_BYTES) {
    return `파일이 ${sizeLabel(file.size)} 입니다. ${sizeLabel(MAX_PDF_BYTES)} 까지 올릴 수 있습니다.`
  }
  if (file.size === 0) return '내용이 없는 파일입니다. 다른 파일을 골라 주세요.'
  return null
}

/** 읽기가 실패했을 때. 화면은 message 를 그대로 보여 줍니다. */
export class BusinessLicenseReadError extends Error {}

const MOCK_DELAY_MS = 1200

/**
 * 사업자등록증에서 값을 읽습니다.
 *
 * TODO: 백엔드가 생기면 이 안을 `POST /business-licenses/scan` 호출로 바꿉니다.
 * 지금은 읽는 데 걸리는 시간만 흉내 내고 빈 초안을 돌려줍니다. 사람이 등록 폼에서
 * 직접 채우게 두는 편이, 그럴듯한 가짜 값을 채워 넣어 진짜로 오해하게 하는 것보다 낫습니다.
 */
export function extractBusinessLicense(file: File): Promise<BusinessLicenseDraft> {
  return new Promise((resolve, reject) => {
    window.setTimeout(() => {
      const problem = pdfProblem(file)
      if (problem !== null) {
        reject(new BusinessLicenseReadError(problem))
        return
      }
      resolve({ ...EMPTY_DRAFT })
    }, MOCK_DELAY_MS)
  })
}
