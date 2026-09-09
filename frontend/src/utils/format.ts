/** 28400000 → ₩28.4M. 요약 카드처럼 자리가 좁은 곳에서 씁니다. */
export function won(n: number): string {
  return `₩${(n / 1_000_000).toFixed(1)}M`
}

/** 28400000 → ₩28,400,000. 금액을 정확히 보여야 하는 곳에서 씁니다. */
export function wonFull(n: number): string {
  return `₩${n.toLocaleString('ko-KR')}`
}

/**
 * 1234567890 → 123-45-67890. 저장은 숫자 10자리로 하고 하이픈은 화면에서만 붙입니다.
 *
 * 값이 없거나 10자리가 아니면 null 입니다. 부르는 쪽이 대체 문구를 정합니다.
 */
export function formatBusinessNo(value: string | null | undefined): string | null {
  if (!value) return null
  const digits = value.replaceAll(/\D/g, '')
  if (digits.length !== 10) return null
  return `${digits.slice(0, 3)}-${digits.slice(3, 5)}-${digits.slice(5)}`
}

/** 사용자가 하이픈을 넣어 적어도 저장 형식(숫자만)으로 되돌립니다. */
export function businessNoDigits(value: string): string {
  return value.replaceAll(/\D/g, '')
}

/** 전화번호를 저장 형식(숫자만)으로 되돌립니다. 하이픈·공백·국가번호 기호를 걷어냅니다. */
export function phoneDigits(value: string): string {
  return value.replaceAll(/\D/g, '')
}

/**
 * 01012345678 → 010-1234-5678. 저장은 숫자만 하고 하이픈은 화면에서만 붙입니다.
 *
 * 입력 중인 짧은 값도 그대로 다루므로 입력칸의 자동 하이픈에 함께 씁니다.
 * 국내 번호 모양이 아니면 숫자를 그대로 돌려줍니다. 해외 번호가 화면에서 사라지면 안 됩니다.
 */
export function formatPhone(value: string | null | undefined): string {
  const d = phoneDigits(value ?? '')
  if (d.length <= 3) return d
  // 서울 지역번호만 두 자리입니다.
  if (d.startsWith('02')) {
    if (d.length <= 5) return `${d.slice(0, 2)}-${d.slice(2)}`
    if (d.length <= 9) return `${d.slice(0, 2)}-${d.slice(2, 5)}-${d.slice(5)}`
    if (d.length === 10) return `${d.slice(0, 2)}-${d.slice(2, 6)}-${d.slice(6)}`
    return d
  }
  // 1588 같은 대표번호는 지역번호가 없습니다.
  if (/^1[0-9]{3}/.test(d) && d.length <= 8) {
    return d.length <= 4 ? d : `${d.slice(0, 4)}-${d.slice(4)}`
  }
  if (d.length <= 7) return `${d.slice(0, 3)}-${d.slice(3)}`
  if (d.length <= 10) return `${d.slice(0, 3)}-${d.slice(3, 6)}-${d.slice(6)}`
  if (d.length === 11) return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}`
  return d
}

/**
 * 입력 중인 사업자 등록번호에 하이픈을 붙입니다.
 *
 * 다 적기 전에도 보정해야 하므로, 10자리가 아니면 null 을 주는 formatBusinessNo 와 나눠 둡니다.
 */
export function maskBusinessNo(value: string): string {
  const d = businessNoDigits(value).slice(0, 10)
  if (d.length <= 3) return d
  if (d.length <= 5) return `${d.slice(0, 3)}-${d.slice(3)}`
  return `${d.slice(0, 3)}-${d.slice(3, 5)}-${d.slice(5)}`
}
