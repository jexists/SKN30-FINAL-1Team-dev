import { useCallback, useEffect, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import type { PageResponse, ProductCreateRequest, ProductResponse } from '@/types'

const PAGE_LIMIT = 100

const byName = (a: ProductResponse, b: ProductResponse) => a.name.localeCompare(b.name, 'ko')

async function fetchAll(signal: AbortSignal): Promise<ProductResponse[]> {
  // ponytail: 상품 마스터는 팀당 수십 건이라 전건을 받습니다. 늘어나면 서버 페이지로 바꿉니다.
  const items: ProductResponse[] = []
  let skip = 0

  while (!signal.aborted) {
    const { data } = await client.get<PageResponse<ProductResponse>>('/products', {
      params: { skip, limit: PAGE_LIMIT },
      signal,
    })
    items.push(...data.items)
    if (!data.has_more || data.next_skip === null) break
    if (data.next_skip <= skip) throw new Error('invalid_pagination')
    skip = data.next_skip
  }

  return items
}

export default function useProducts() {
  const [products, setProducts] = useState<ProductResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    void fetchAll(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setProducts(items)
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          setError(errorMessage(caught, '상품 목록을 불러오지 못했습니다.'))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [reloadKey])

  const reload = useCallback(() => setReloadKey((previous) => previous + 1), [])

  /**
   * 자료실(useDocuments.addDocument)과 같은 2단계입니다. 상품을 먼저 만들고
   * 사진이 있으면 그 뒤에 붙입니다. 사진 업로드가 실패해도 상품은 남습니다.
   */
  const addProduct = useCallback(async (payload: ProductCreateRequest, image: File | null) => {
    const { data: created } = await client.post<ProductResponse>('/products', payload)
    let product = created
    if (image !== null) {
      const form = new FormData()
      form.append('upload', image)
      const { data } = await client.put<ProductResponse>(`/products/${created.id}/image`, form)
      product = data
    }
    setProducts((previous) => [...previous, product].sort(byName))
    return product
  }, [])

  return { products, loading, error, reload, addProduct }
}
