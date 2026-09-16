// 제품 한 건의 요약. 견적 폼 옆 패널과 영업자료의 연결 상품 패널이 같이 씁니다.
//
// 상품관리 화면은 팀장만 들어가므로, 다른 화면에서는 이것으로 읽기만 합니다.
import { useEffect, useState } from 'react'

import { client } from '@/api/client'
import { ProductIcon } from '@/components/icons'
import type { PageResponse, ProductResponse } from '@/types'
import { wonFull } from '@/utils/format'

import { categoryLabel, shelfLifeLabel } from '../catalog'
import useProductImage from '../useProductImage'

import styles from './ProductSummary.module.scss'

interface Picked {
  id: string
  name: string
}

// 한 번 받은 제품은 모달을 다시 열어도 다시 받지 않습니다.
const cache = new Map<string, ProductResponse>()

/**
 * ponytail: 제품 한 건을 받는 GET 이 없어 이름으로 검색해 id 가 같은 줄을 씁니다.
 * 같은 이름이 30건을 넘으면 못 찾을 수 있습니다. 그때 GET /products/{id} 를 추가합니다.
 */
function useProduct(picked: Picked): ProductResponse | null | 'missing' {
  const [product, setProduct] = useState<ProductResponse | null | 'missing'>(
    () => cache.get(picked.id) ?? null,
  )

  useEffect(() => {
    const hit = cache.get(picked.id)
    if (hit) {
      setProduct(hit)
      return
    }
    setProduct(null)
    const controller = new AbortController()
    void client
      .get<PageResponse<ProductResponse>>('/products', {
        params: { q: picked.name.slice(0, 100), limit: 30 },
        signal: controller.signal,
      })
      .then(({ data }) => {
        const found = data.items.find((row) => row.id === picked.id)
        if (found) cache.set(found.id, found)
        if (!controller.signal.aborted) setProduct(found ?? 'missing')
      })
      .catch(() => {
        if (!controller.signal.aborted) setProduct('missing')
      })
    return () => controller.abort()
  }, [picked.id, picked.name])

  return product
}

export default function ProductSummary({ picked }: { picked: Picked }) {
  const product = useProduct(picked)

  if (product === null) return <p className={styles.state}>제품 정보를 불러오는 중입니다.</p>
  if (product === 'missing')
    return (
      <p className={styles.state}>
        제품 정보를 불러오지 못했습니다. 사용 중지된 제품일 수 있습니다.
      </p>
    )
  return <Loaded product={product} />
}

function Loaded({ product }: { product: ProductResponse }) {
  const url = useProductImage(product)
  const facts: [string, string | null][] = [
    [
      '유효기간',
      product.shelf_life_months === null ? null : shelfLifeLabel(product.shelf_life_months),
    ],
    ['규격', product.spec || null],
    ['비고', product.memo || null],
  ]

  // 이름은 패널 머리말·탭이 이미 보여 줍니다. 여기서는 분류와 단가부터 읽힙니다.
  return (
    <article className={styles.detail}>
      {url !== null && <img className={styles.photo} src={url} alt={`${product.name} 사진`} />}

      <header className={styles.head}>
        {/* 사진이 없으면 큰 빈칸 대신 작은 표식만 둡니다. */}
        {url === null && (
          <span className={styles.thumb} aria-hidden="true">
            <ProductIcon width={20} height={20} strokeWidth={1.5} />
          </span>
        )}
        <div className={styles.headText}>
          <span className={styles.category}>{categoryLabel(product.category_code)}</span>
          <strong className={`${styles.price} tnum`}>{wonFull(product.unit_price)}</strong>
        </div>
      </header>

      <dl className={styles.facts}>
        {facts.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd className={value === null ? styles.none : undefined}>{value ?? '없음'}</dd>
          </div>
        ))}
      </dl>
    </article>
  )
}
