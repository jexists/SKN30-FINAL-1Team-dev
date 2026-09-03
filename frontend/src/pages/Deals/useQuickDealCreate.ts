// 딜 화면 바깥에서 딜 한 건을 그 자리에서 만들 때 쓰는 최소 묶음입니다.
//
// 일정 등록처럼 "고를 딜이 없어서 막히는" 자리에 씁니다. useSalesDeals 는 보드와 목록이
// 쓰는 것이라 딜 전건과 상태 목록까지 받으므로, 딜 하나 만들자고 부르기에는 큽니다.
// 여기서는 단계 목록과 등록 한 번만 들고 갑니다.
import { useCallback, useEffect, useState } from 'react'

import { client } from '@/api/client'
import type { SalesDealResponse, SalesPipelineResponse, SalesPipelineStageResponse } from '@/types'

import {
  toColumn,
  toCreateRequest,
  toSalesDeal,
  type SalesDeal,
  type SalesDealColumn,
  type SalesDealSaveInput,
} from './useSalesDeals'

export default function useQuickDealCreate() {
  const [columns, setColumns] = useState<SalesDealColumn[]>([])
  const [pipelineId, setPipelineId] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    void client
      .get<SalesPipelineResponse[]>('/sales-pipelines', { signal: controller.signal })
      .then(async ({ data }) => {
        // 딜 보드가 고르는 것과 같은 파이프라인입니다. 기본으로 표시된 게시본이 없으면
        // 게시본 아무거나, 그것도 없으면 첫 벌을 봅니다.
        const pipeline =
          data.find(({ is_default, status_code }) => is_default && status_code === 'published') ??
          data.find(({ status_code }) => status_code === 'published') ??
          data[0]
        if (pipeline === undefined) return

        const { data: stages } = await client.get<SalesPipelineStageResponse[]>(
          `/sales-pipelines/${pipeline.id}/stages`,
          { signal: controller.signal },
        )
        if (controller.signal.aborted) return
        setPipelineId(pipeline.id)
        setColumns(stages.map(toColumn))
      })
      // 못 받으면 "새 딜 만들기" 를 띄우지 않습니다. 부르는 쪽이 ready 로 가립니다.
      .catch(() => {})

    return () => controller.abort()
  }, [])

  const createDeal = useCallback(
    async (input: SalesDealSaveInput): Promise<SalesDeal> => {
      if (pipelineId === null) throw new Error('사용할 영업 파이프라인이 없습니다.')
      const { data } = await client.post<SalesDealResponse>(
        '/sales-deals',
        toCreateRequest(input, pipelineId),
      )
      return toSalesDeal(data)
    },
    [pipelineId],
  )

  return { columns, ready: pipelineId !== null && columns.length > 0, createDeal }
}
