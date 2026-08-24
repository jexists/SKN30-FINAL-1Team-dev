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
