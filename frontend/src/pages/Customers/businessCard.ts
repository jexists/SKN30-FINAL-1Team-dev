// 명함 이미지에서 고객 정보를 읽어 내는 자리.
//
// 화면과 흐름은 다 있고 인식만 아직 붙지 않았습니다. 백엔드에 인식 엔드포인트가
// 생기면 recognizeBusinessCard 한 곳만 고치면 됩니다. 나머지는 손댈 것이 없습니다.
//
//   const form = new FormData()
//   form.append('image', image)
//   const { data } = await client.post<BusinessCardDraft>('/business-cards/scan', form)
//   return data

/** 명함에서 읽어 낸 값. 고객 등록 폼의 칸과 이름을 맞춰 둡니다. */
export interface BusinessCardDraft {
  org: string
  name: string
  dept: string
  title: string
  email: string
  phone: string
}

/** 인식이 아직 연결되지 않았습니다. 화면은 직접 입력으로 이어 갑니다. */
export class BusinessCardUnavailableError extends Error {
  constructor() {
    super('명함 인식이 아직 연결되지 않았습니다.')
    this.name = 'BusinessCardUnavailableError'
  }
}

/** 명함 이미지 한 장을 읽습니다. */
export function recognizeBusinessCard(_image: File): Promise<BusinessCardDraft> {
  return Promise.reject(new BusinessCardUnavailableError())
}

/** 명함 한 장이면 충분한 크기입니다. 더 큰 사진은 인식이 아니라 전송에서 막힙니다. */
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024
