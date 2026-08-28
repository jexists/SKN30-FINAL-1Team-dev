// 다음(카카오) 우편번호 서비스를 필요할 때만 불러옵니다.
//
// index.html 에 넣으면 주소를 쓰지 않는 화면까지 외부 스크립트를 내려받게 됩니다.
// 주소 검색 버튼을 처음 누를 때 한 번만 붙이고, 그 뒤로는 같은 Promise 를 돌려줍니다.

const SCRIPT_SRC = 'https://t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js'

/** 우편번호 창이 고른 주소. 쓰는 값만 적었습니다. */
export interface DaumPostcodeResult {
  /** 우편번호 5자리 */
  zonecode: string
  roadAddress: string
  jibunAddress: string
  /** 건물 이름. 없으면 빈 문자열입니다. */
  buildingName: string
  /** 'R' 도로명 / 'J' 지번. 고른 사람이 보고 있던 쪽입니다. */
  userSelectedType: 'R' | 'J'
}

interface DaumPostcodeOptions {
  oncomplete: (result: DaumPostcodeResult) => void
  onclose?: () => void
}

interface DaumPostcodeInstance {
  open: () => void
}

type DaumPostcodeConstructor = new (options: DaumPostcodeOptions) => DaumPostcodeInstance

declare global {
  interface Window {
    daum?: { Postcode?: DaumPostcodeConstructor }
  }
}

let pending: Promise<DaumPostcodeConstructor> | null = null

export function loadDaumPostcode(): Promise<DaumPostcodeConstructor> {
  const loaded = window.daum?.Postcode
  if (loaded !== undefined) return Promise.resolve(loaded)
  if (pending !== null) return pending

  pending = new Promise<DaumPostcodeConstructor>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = SCRIPT_SRC
    script.async = true
    script.onload = () => {
      const constructor = window.daum?.Postcode
      if (constructor === undefined) {
        reject(new Error('우편번호 서비스를 불러오지 못했습니다.'))
        return
      }
      resolve(constructor)
    }
    script.onerror = () => reject(new Error('우편번호 서비스를 불러오지 못했습니다.'))
    document.head.append(script)
  })

  // 실패한 Promise 를 남겨 두면 다시 눌러도 같은 실패만 돌아옵니다.
  pending.catch(() => {
    pending = null
  })

  return pending
}

/** 고른 결과에서 화면에 넣을 주소 한 줄을 만듭니다. */
export function pickAddress(result: DaumPostcodeResult): string {
  const base = result.userSelectedType === 'R' ? result.roadAddress : result.jibunAddress
  return result.buildingName === '' ? base : `${base} (${result.buildingName})`
}
