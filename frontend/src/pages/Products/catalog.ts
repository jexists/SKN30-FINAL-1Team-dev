import type { ProductCategoryCode } from '@/types'

export const CATEGORIES: { code: ProductCategoryCode; label: string }[] = [
  { code: 'system', label: '시스템' },
  { code: 'probe', label: '프로브' },
  { code: 'consumable', label: '소모품' },
]

const LABEL_BY_CODE = new Map(CATEGORIES.map(({ code, label }) => [code, label]))

/** 백엔드가 아직 모르는 코드를 보내도 화면이 비지 않게 코드를 그대로 씁니다. */
export function categoryLabel(code: string): string {
  return LABEL_BY_CODE.get(code as ProductCategoryCode) ?? code
}

export function shelfLifeLabel(months: number | null): string {
  return months === null ? '-' : `${months}개월`
}
