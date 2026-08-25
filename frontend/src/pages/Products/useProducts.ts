import { useCallback, useEffect, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import type { PageResponse, ProductCreateRequest, ProductResponse } from '@/types'

import { categoryCodesMatching } from './catalog'

export interface ProductQuery {
  q: string
  skip: number
  limit: number
}

export default function useProducts({ q, skip, limit }: ProductQuery) {
  const [products, setProducts] = useState<ProductResponse[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const needle = q.trim()

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    void client
      .get<PageResponse<ProductResponse>>('/products', {
        params: {
          q: needle === '' ? undefined : needle.slice(0, 100),
          // 분류 이름("소모품")으로도 찾습니다. 그 이름은 화면만 알고 있으므로 풀어서
          // 보내고 서버가 q 와 OR 로 묶습니다.
          q_category_code: needle === '' ? undefined : categoryCodesMatching(needle),
          skip,
          limit,
        },
        signal: controller.signal,
      })
      .then(({ data }) => {
        if (controller.signal.aborted) return
        setProducts(data.items)
        setTotal(data.total)
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
  }, [needle, skip, limit, reloadKey])

  const reload = useCallback(() => setReloadKey((previous) => previous + 1), [])

  /**
   * 자료실(useDocuments.addDocument)과 같은 2단계입니다. 상품을 먼저 만들고
   * 사진이 있으면 그 뒤에 붙입니다. 사진 업로드가 실패해도 상품은 남습니다.
   */
  const addProduct = useCallback(
    async (payload: ProductCreateRequest, image: File | null) => {
      const { data: created } = await client.post<ProductResponse>('/products', payload)
      let product = created
      if (image !== null) {
        const form = new FormData()
        form.append('upload', image)
        const { data } = await client.put<ProductResponse>(`/products/${created.id}/image`, form)
        product = data
      }
      // 새 상품이 이 페이지에 속하는지는 이름 순서가 정합니다. 목록에 끼워 넣지 않고
      // 다시 받아 서버가 정한 자리에 놓습니다.
      reload()
      return product
    },
    [reload],
  )

  return { products, total, loading, error, reload, addProduct }
}
