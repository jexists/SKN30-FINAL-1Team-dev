import { ProductIcon } from '@/components/icons'
import type { ProductResponse } from '@/types'

import useProductImage from '../useProductImage'

import styles from '../Products.module.scss'

/** 목록 한 줄의 상품 사진. 주소를 받아 오는 일은 useProductImage 가 맡습니다. */
export default function ProductThumb({ product }: { product: ProductResponse }) {
  const url = useProductImage(product)

  if (url === null) {
    return (
      <span className={styles.thumbEmpty} aria-hidden="true">
        <ProductIcon width={16} height={16} strokeWidth={1.5} />
      </span>
    )
  }
  return <img className={styles.thumb} src={url} alt={`${product.name} 사진`} loading="lazy" />
}
