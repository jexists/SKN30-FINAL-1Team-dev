// 이 미팅의 고객사에 걸린 영업 현황을 받아 옵니다.
//
// 보고서 작성 화면에서 "무엇에 대한 미팅이었는지" 를 고르는 목록입니다. 한 회사에
// 딜이 수십 건씩 쌓이는 곳은 아직 없어 첫 쪽만 받고 더 받지 않습니다. 목록이 길어지면
// Deals 화면처럼 페이징을 붙일 자리입니다.
import { useCallback, useEffect, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import { toSalesDeal, type SalesDeal } from '@/pages/Deals/useSalesDeals'
import type { PageResponse, SalesDealResponse } from '@/types'

/** 서버가 한 쪽에 주는 최대치입니다. SalesDealPageParams 가 30 을 넘기면 거절합니다. */
const LIMIT = 30

export default function useCompanyDeals(companyId?: string | null) {
  const [deals, setDeals] = useState<SalesDeal[]>([])
  const [loading, setLoading] = useState(Boolean(companyId))
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    if (!companyId) {
      setDeals([])
      setLoading(false)
      setError(null)
      return
    }

    const controller = new AbortController()
    setLoading(true)
    setError(null)
    client
      .get<PageResponse<SalesDealResponse>>('/sales-deals', {
        params: { customer_company_id: companyId, limit: LIMIT },
        signal: controller.signal,
      })
      .then(({ data }) => {
        setDeals(data.items.map(toSalesDeal))
        setLoading(false)
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        setError(errorMessage(cause, '영업 현황을 불러오지 못했습니다.'))
        setLoading(false)
      })
    return () => controller.abort()
  }, [companyId, reloadKey])

  const reload = useCallback(() => setReloadKey((key) => key + 1), [])

  return { deals, loading, error, reload }
}
