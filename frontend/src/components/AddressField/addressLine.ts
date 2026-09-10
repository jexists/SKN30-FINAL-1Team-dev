// 한 줄로 보여 주는 주소를 만들고 되읽는 규칙입니다.
//
// 칸이 하나라 고른 주소와 사람이 적은 상세주소가 같은 줄에 섞입니다. 경계는 `head`
// 하나이고, 그 앞은 우편번호 창이 정한 값이라 사람이 고칠 수 없습니다.

export interface AddressValue {
  postcode: string
  address: string
  addressDetail: string
}

/** 사람이 고친 부분과 고른 부분의 경계. 우편번호는 괄호에 넣습니다. */
export function addressHead({ postcode, address }: AddressValue): string {
  if (address === '') return ''
  return postcode === '' ? address : `(${postcode}) ${address}`
}

/** 한 줄로 읽히는 주소 전체. 상세주소는 뒤에 이어 붙습니다. */
export function formatAddress(value: AddressValue): string {
  const head = addressHead(value)
  if (head === '') return ''
  return value.addressDetail === '' ? head : `${head} ${value.addressDetail}`
}

/**
 * 한 줄을 고쳐 친 결과를 되읽습니다.
 *
 * 고른 주소가 그대로 남아 있으면 뒤에 붙은 만큼이 상세주소입니다. 주소가 아직 없거나
 * 앞부분이 지워졌으면 다시 고르겠다는 뜻이라 `null` 입니다 — 부르는 쪽이 우편번호 창을
 * 엽니다. 값을 반쯤 지워진 채로 두지 않습니다.
 */
export function readAddressLine(value: AddressValue, typed: string): AddressValue | null {
  const head = addressHead(value)
  if (head === '' || !typed.startsWith(head)) return null
  return { ...value, addressDetail: typed.slice(head.length).trimStart() }
}

/**
 * 커서가 그 자리에서 무엇을 뜻하는지. 주소 부분 안이면 다시 고르는 것이고, 줄 끝이면
 * 상세주소를 적으려는 것입니다. 아직 주소가 없으면 어디를 눌러도 고르는 자리입니다.
 */
export function caretPicksAddress(value: AddressValue, caret: number | null): boolean {
  const head = addressHead(value)
  return head === '' || caret === null || caret < head.length
}
