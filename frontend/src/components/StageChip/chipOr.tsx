import type { ReactNode } from 'react'

import type { ColumnTone } from '@/types'

import StageChip from './StageChip'

/**
 * 아직 없을 수 있는 상태를 그립니다. 견적·계약·발주는 딜이 그 단계에 닿기 전까지
 * 비어 있어, 네 화면이 저마다 같은 null 검사를 적지 않도록 여기에 둡니다.
 */
export function chipOr(tone: ColumnTone | null, name: string | null): ReactNode {
  if (tone === null || name === null) return '-'
  return <StageChip tone={tone}>{name}</StageChip>
}
