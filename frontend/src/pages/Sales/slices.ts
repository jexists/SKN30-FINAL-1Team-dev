// 계열 색을 정하는 자리. 왼쪽 표와 오른쪽 패널이 같은 규칙을 봐야 같은 회사가
// 두 곳에서 같은 색으로 보입니다. 색이 갈리면 두 패널이 한 화면으로 안 읽힙니다.
//
// 매출 계열은 --red·--green 을 쓰지 않습니다. 이 앱에서 그 둘은 '취소'와 '상승'이라
// 뜻이 정해져 있어, 계열색으로 쓰면 옆에 붙는 증감 표시와 의미가 섞입니다.
import type { SalesGroup } from './useSalesSummary'

/** 상위 몇 개까지 고유한 색을 줄지. 색이 계열보다 적으면 색이 겹쳐 읽을 수 없게 됩니다. */
export const TOP = 5

const RANKED = [
  'var(--sales-1)',
  'var(--sales-2)',
  'var(--sales-3)',
  'var(--sales-4)',
  'var(--sales-5)',
]

/** 상위권 밖과 금액 0원 몫 */
export const REST_COLOR = 'var(--sales-6)'

/**
 * 금액 내림차순으로 정렬된 목록에서 index 번째가 쓸 색.
 * 금액이 0이면 순위와 무관하게 회색입니다. 매출에 기여하지 않은 줄이기 때문입니다.
 */
export function colorOf(index: number, value: number): string {
  return value > 0 && index < TOP ? RANKED[index] : REST_COLOR
}

export interface Slice {
  key: string
  value: number
  color: string
  /** '기타' 가 몇 개를 묶었는지. 나머지 슬라이스는 1 입니다. */
  count: number
}

/** 상위 TOP 개 + 나머지를 묶은 '기타'. 금액이 0인 그룹은 빠집니다. */
export function toSlices(groups: SalesGroup[]): Slice[] {
  const scored = groups.filter((g) => g.actual > 0)
  const head = scored.slice(0, TOP).map((g, i) => ({
    key: g.key,
    value: g.actual,
    color: colorOf(i, g.actual),
    count: 1,
  }))

  const rest = scored.slice(TOP)
  if (rest.length === 0) return head

  return [
    ...head,
    {
      key: `기타 ${rest.length}개`,
      value: rest.reduce((sum, g) => sum + g.actual, 0),
      color: REST_COLOR,
      count: rest.length,
    },
  ]
}
