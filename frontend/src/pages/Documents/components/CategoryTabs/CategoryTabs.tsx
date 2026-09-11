// 분류 탭. 지금 보고 있는 방이 담는 문서 종류를 그대로 탭으로 씁니다.
//
// 옆의 건수는 검색·등록자·기간까지만 적용한 수입니다. 분류까지 적용하면 고른 탭만
// 숫자가 남고 나머지가 0 이 되어 어디에 몇 건이 있는지 알 수 없습니다.
import Tabs, { type TabItem } from '@/components/Tabs'
import type { DocumentCategory } from '@/types'

import { TONE_OF } from '../../catalog'

interface Props {
  /** 고른 분류. 빈 문자열이면 전체입니다. */
  value: string
  /** 이 방이 담는 분류. 방마다 다릅니다. */
  categories: readonly DocumentCategory[]
  countOf: (category: DocumentCategory) => number
  total: number
  onChange: (category: string) => void
}

export default function CategoryTabs({ value, categories, countOf, total, onChange }: Props) {
  const items: TabItem[] = [
    { value: '', label: '전체', count: total },
    ...categories.map((category) => ({
      value: category,
      label: category,
      count: countOf(category),
      tone: TONE_OF[category],
    })),
  ]

  return <Tabs items={items} value={value} label="자료 분류" onChange={onChange} />
}
