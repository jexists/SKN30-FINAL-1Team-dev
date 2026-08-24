import { useEffect, useState } from 'react'

import { client } from '@/api/client'
import { ProductIcon } from '@/components/icons'
import type { ProductImageResponse, ProductResponse } from '@/types'

import styles from '../Products.module.scss'

/**
 * 상품 사진 한 장. 저장소 주소는 내보내지 않으므로 짧게 사는 서명 URL 을 따로 받습니다.
 *
 * ponytail: 사진이 있는 줄마다 한 번씩 부릅니다. 상품이 많아지면 한 번에 여러 건을
 * 발급받는 방식으로 바꿉니다. 주소는 5분이면 만료하므로 화면을 오래 열어 두면
 * 사진 자리가 빕니다. 그때는 새로고침이 답입니다.
 */
export default function ProductThumb({ product }: { product: ProductResponse }) {
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    setUrl(null)
    if (!product.has_image) return

    const controller = new AbortController()
    void client
      .get<ProductImageResponse>(`/products/${product.id}/image`, { signal: controller.signal })
      .then(({ data }) => {
        if (!controller.signal.aborted) setUrl(data.url)
      })
      .catch(() => {
        // 사진 한 장을 못 받았다고 목록 전체가 실패하지는 않습니다. 자리표시자로 둡니다.
      })

    return () => controller.abort()
  }, [product.id, product.has_image])

  if (url === null) {
    return (
      <span className={styles.thumbEmpty} aria-hidden="true">
        <ProductIcon width={16} height={16} strokeWidth={1.5} />
      </span>
    )
  }
  return <img className={styles.thumb} src={url} alt={`${product.name} 사진`} loading="lazy" />
}
