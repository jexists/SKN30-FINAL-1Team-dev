import { useState } from 'react'
import { useSearchParams } from 'react-router'

import Button from '@/components/Button'
import ErrorToast from '@/components/ErrorToast'
import { PlusIcon, ProductIcon, SearchIcon } from '@/components/icons'
import Pagination, { PAGE_SIZE } from '@/components/Pagination'
import SearchInput from '@/components/SearchInput'
import { ListPageSkeleton, TableSkeleton } from '@/components/Skeleton'
import { wonFull } from '@/utils/format'

import { categoryLabel, shelfLifeLabel } from './catalog'
import ProductFormModal from './components/ProductFormModal'
import ProductThumb from './components/ProductThumb'
import useProducts from './useProducts'

import styles from './Products.module.scss'

const COLUMNS = [
  { id: 'image', header: '사진', width: 72 },
  { id: 'name', header: '제품명', width: 220 },
  { id: 'category', header: '분류', width: 96 },
  { id: 'price', header: '제품단가', width: 132 },
  { id: 'shelfLife', header: '유효기간', width: 96 },
  { id: 'memo', header: '메모', width: 420 },
]

const TABLE_WIDTH = COLUMNS.reduce((sum, column) => sum + column.width, 0)

export default function Products() {
  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const [adding, setAdding] = useState(false)
  const [page, setPage] = useState(1)

  const {
    products: rows,
    total,
    loading,
    error,
    reload,
    addProduct,
  } = useProducts({ q: query, skip: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE })

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  // 검색어가 바뀌면 결과가 줄어 지금 쪽수가 범위를 넘을 수 있습니다. 첫 쪽으로 돌립니다.
  const setQuery = (value: string) => {
    const next = new URLSearchParams(params)
    if (value === '') next.delete('q')
    else next.set('q', value)
    setParams(next, { replace: true })
    setPage(1)
  }

  // 고객불만 목록과 같은 처리입니다. 첫 진입에서 툴바·표가 따로 들어오면
  // 화면이 두 번 들썩이므로 한 장을 통째로 자리표시자로 둡니다.
  if (loading && rows.length === 0 && !error) {
    return (
      <section className={styles.page} aria-busy={loading}>
        <h1 className="sr-only">상품관리</h1>
        <ListPageSkeleton label="상품 목록을 불러오는 중입니다." />
      </section>
    )
  }

  return (
    <section className={styles.page} aria-busy={loading}>
      <h1 className="sr-only">상품관리</h1>

      <div className={styles.toolbar}>
        <SearchInput
          className={styles.search}
          value={query}
          placeholder="제품명·분류·메모 검색"
          label="상품 검색"
          onSearch={setQuery}
        />
        <div className={styles.actions}>
          <Button disabled={loading} onClick={() => setAdding(true)}>
            <PlusIcon width={15} height={15} />
            상품 등록
          </Button>
        </div>
      </div>

      <ErrorToast message={error} onRetry={reload} />

      {!error && loading ? (
        <TableSkeleton label="상품 목록을 새로고침하는 중입니다." rows={rows.length} />
      ) : rows.length === 0 ? (
        <div className={styles.card}>
          <div className={styles.empty}>
            {query.trim() !== '' ? (
              <>
                <SearchIcon width={34} height={34} strokeWidth={1.5} />
                <p>조건에 맞는 상품이 없습니다.</p>
                <Button variant="outline" onClick={() => setQuery('')}>
                  검색 초기화
                </Button>
              </>
            ) : (
              <>
                <ProductIcon width={34} height={34} strokeWidth={1.5} />
                <p>등록된 상품이 없습니다.</p>
                <Button onClick={() => setAdding(true)}>상품 등록</Button>
              </>
            )}
          </div>
        </div>
      ) : (
        <div className={styles.card}>
          {/* 좁은 화면에서는 표가 카드 안에서만 옆으로 흐릅니다. */}
          <div className={styles.scroller}>
            <table className={styles.table} style={{ width: TABLE_WIDTH }}>
              <caption className="sr-only">등록된 상품 목록</caption>
              <colgroup>
                {COLUMNS.map((column) => (
                  <col key={column.id} style={{ width: column.width }} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  {COLUMNS.map((column) => (
                    <th key={column.id} scope="col">
                      {column.header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((product) => (
                  <tr key={product.id}>
                    <td>
                      <ProductThumb product={product} />
                    </td>
                    <td className={styles.name} title={product.name}>
                      {product.name}
                    </td>
                    <td>
                      <i className={styles.badge}>{categoryLabel(product.category_code)}</i>
                    </td>
                    <td className="tnum">{wonFull(product.unit_price)}</td>
                    <td className="tnum">{shelfLifeLabel(product.shelf_life_months)}</td>
                    <td className={styles.memo} title={product.memo ?? ''}>
                      {product.memo ?? '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Pagination page={page} pageCount={pageCount} total={total} unit="개" onPage={setPage} />
        </div>
      )}

      {adding && (
        <ProductFormModal
          onClose={() => setAdding(false)}
          onSubmit={async (payload, image) => {
            await addProduct(payload, image)
            setAdding(false)
          }}
        />
      )}
    </section>
  )
}
