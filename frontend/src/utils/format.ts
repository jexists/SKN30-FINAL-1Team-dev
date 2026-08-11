/** 28400000 → ₩28.4M. 요약 카드처럼 자리가 좁은 곳에서 씁니다. */
export function won(n: number): string {
  return `₩${(n / 1_000_000).toFixed(1)}M`
}

/** 28400000 → ₩28,400,000. 금액을 정확히 보여야 하는 곳에서 씁니다. */
export function wonFull(n: number): string {
  return `₩${n.toLocaleString('ko-KR')}`
}
