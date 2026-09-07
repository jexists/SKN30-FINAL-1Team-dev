/**
 * 담당자 이름표처럼 "고른 색을 그대로 쓰는" 자리의 글자색을 정합니다.
 *
 * 팀장이 고른 바탕색은 손대지 않습니다. 진한 남색을 골랐으면 진한 남색으로 칠합니다.
 * 대신 그 위에 얹는 글자만 검정 계열과 흰색 중에서 읽히는 쪽으로 바꿉니다. 바탕을
 * 연하게 눌러 읽히게 만들면 팀장이 고른 색이 아닌 다른 색이 화면에 서게 됩니다.
 */

/** `#rrggbb` 또는 `#RGB`. 색 입력칸과 서버가 모두 이 모양만 주고받습니다. */
const HEX = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i

/** sRGB 채널 하나를 선형값으로 되돌립니다. WCAG 상대휘도 정의 그대로입니다. */
function linear(channel: number): number {
  const value = channel / 255
  return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
}

/** 0(검정)~1(흰색). 밝기 판단에만 씁니다. */
export function luminance(hex: string): number | null {
  if (!HEX.test(hex)) return null
  const body = hex.slice(1)
  // #abc 는 #aabbcc 와 같은 색입니다.
  const full =
    body.length === 3
      ? body
          .split('')
          .map((digit) => digit + digit)
          .join('')
      : body
  const [r, g, b] = [0, 2, 4].map((offset) => Number.parseInt(full.slice(offset, offset + 2), 16))
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)
}

/**
 * 이 바탕색 위에서 읽히는 글자색입니다.
 *
 * 밝은 바탕에는 기존 잉크 토큰을 그대로 씁니다. 순수한 검정을 쓰면 회색 이름표만 다른
 * 화면과 다른 글자색을 갖게 됩니다. 어두운 바탕에서만 흰색으로 뒤집습니다.
 *
 * 경계값 0.45 는 흰 글자와 검은 글자의 대비가 뒤집히는 지점(약 0.18)보다 위입니다.
 * 중간 밝기에서는 어두운 글자가 더 또렷해서, 뒤집는 쪽을 늦게 잡았습니다.
 */
export function readableInk(hex: string): string {
  const value = luminance(hex)
  if (value === null) return 'var(--ink)'
  return value < 0.45 ? '#ffffff' : 'var(--ink)'
}
