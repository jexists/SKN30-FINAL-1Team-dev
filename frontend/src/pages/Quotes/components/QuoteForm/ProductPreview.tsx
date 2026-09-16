// 견적에 고른 제품을 폼 옆에서 확인하는 패널입니다.
//
// 품목 칸에는 이름만 남아 규격·사진을 보려면 상품 화면을 따로 열어야 했습니다.
// 한 견적에 제품이 여러 개라 제품마다 탭으로 나눕니다.
import { useState } from 'react'

import type { ItemState } from '@/components/ItemRows'
import Tabs from '@/components/Tabs'
import ProductSummary from '@/pages/Products/components/ProductSummary'

import styles from './ProductPreview.module.scss'

interface Picked {
  id: string
  name: string
}

/** 품목 중 제품을 고른 줄만, 같은 제품은 한 번만. */
function pickedProducts(items: ItemState[]): Picked[] {
  const seen = new Map<string, Picked>()
  for (const item of items) {
    if (item.productId !== '' && !seen.has(item.productId))
      seen.set(item.productId, { id: item.productId, name: item.productName })
  }
  return [...seen.values()]
}

export default function ProductPreview({ items }: { items: ItemState[] }) {
  const products = pickedProducts(items)
  const ids = products.map((p) => p.id).join(',')
  const [active, setActive] = useState<string | null>(null)
  const [knownIds, setKnownIds] = useState(ids)

  // 새로 고른 제품이 생기면 그 탭을 엽니다. 방금 고른 것을 보고 싶어 하기 때문입니다.
  if (knownIds !== ids) {
    const before = new Set(knownIds.split(','))
    const added = products.find((p) => !before.has(p.id))
    setKnownIds(ids)
    if (added) setActive(added.id)
  }

  const current = products.find((p) => p.id === active) ?? products[0]
  if (!current) return null

  return (
    <div className={styles.root}>
      {/* 한 개여도 탭으로 둡니다. 제품 이름을 보여 주는 자리가 이곳입니다. */}
      <div className={styles.tabs}>
        <Tabs
          label="고른 제품"
          variant="underline"
          size="sm"
          items={products.map((p) => ({ value: p.id, label: p.name }))}
          value={current.id}
          onChange={setActive}
        />
      </div>
      <div className={styles.body}>
        <ProductSummary key={current.id} picked={current} />
      </div>
    </div>
  )
}
