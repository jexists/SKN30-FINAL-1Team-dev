// 상품 한 건의 상세.
//
// 목록은 메모를 한 줄로 자르고 사진도 손톱만 하게 보여 줍니다. 사양·재고·주의사항을
// 끝까지 읽을 자리가 따로 필요해, 상세는 전부 오른쪽 드로어로 연다는 약속을 따릅니다.
//
// 고치는 일은 등록과 같은 폼(ProductFormModal)이 맡습니다. 드로어 안에 입력칸을 또 두면
// 같은 규칙을 두 곳에 적게 됩니다.
import { useState } from 'react'

import Drawer from '@/components/Drawer'
import { EditIcon, MoreIcon, ProductIcon, TrashIcon } from '@/components/icons'
import Popover from '@/components/Popover'
import type { ProductResponse } from '@/types'
import { wonFull } from '@/utils/format'

import { categoryLabel, shelfLifeLabel } from '../../catalog'
import useProductImage from '../../useProductImage'

import styles from './ProductDrawer.module.scss'

interface Props {
  product: ProductResponse
  /** 삭제가 처리되는 동안입니다. 메뉴를 잠급니다. */
  busy: boolean
  onEdit: () => void
  onDelete: () => void
  onClose: () => void
}

export default function ProductDrawer({ product, busy, onEdit, onDelete, onClose }: Props) {
  const [menuOpen, setMenuOpen] = useState(false)
  const url = useProductImage(product)

  return (
    <Drawer
      title={product.name}
      sub={<span className={styles.price}>{wonFull(product.unit_price)}</span>}
      meta={<i className={styles.badge}>{categoryLabel(product.category_code)}</i>}
      actions={
        <Popover
          open={menuOpen}
          onClose={() => setMenuOpen(false)}
          align="end"
          compact
          label="상품 메뉴"
          trigger={
            <button
              type="button"
              className={styles.menuBtn}
              aria-label="상품 메뉴"
              aria-expanded={menuOpen}
              disabled={busy}
              onClick={() => setMenuOpen((value) => !value)}
            >
              <MoreIcon width={18} height={18} />
            </button>
          }
        >
          <div className={styles.menu}>
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false)
                onEdit()
              }}
            >
              <EditIcon width={15} height={15} />
              수정
            </button>
            <button
              type="button"
              className={styles.danger}
              onClick={() => {
                setMenuOpen(false)
                onDelete()
              }}
            >
              <TrashIcon width={15} height={15} />
              삭제
            </button>
          </div>
        </Popover>
      }
      onClose={onClose}
    >
      {/* 사진이 없는 상품도 많습니다. 빈 자리는 자리표시자로 채워 두어야 사진을 아직
          못 받은 것인지 원래 없는 것인지 헷갈리지 않습니다. */}
      {url === null ? (
        <p className={styles.photoEmpty}>
          <ProductIcon width={28} height={28} strokeWidth={1.4} />
          <span>{product.has_image ? '사진을 불러오는 중입니다.' : '등록된 사진이 없습니다.'}</span>
        </p>
      ) : (
        <img className={styles.photo} src={url} alt={`${product.name} 사진`} />
      )}

      <dl className={styles.facts}>
        <div>
          <dt>분류</dt>
          <dd>{categoryLabel(product.category_code)}</dd>
        </div>
        <div>
          <dt>제품단가</dt>
          <dd className="tnum">{wonFull(product.unit_price)}</dd>
        </div>
        <div>
          <dt>유효기간</dt>
          <dd className="tnum">{shelfLifeLabel(product.shelf_life_months)}</dd>
        </div>
      </dl>

      <section className={styles.section}>
        <h3 className={styles.heading}>메모</h3>
        {product.memo === null || product.memo === '' ? (
          <p className={styles.empty}>남긴 메모가 없습니다.</p>
        ) : (
          <p className={styles.memo}>{product.memo}</p>
        )}
      </section>
    </Drawer>
  )
}
