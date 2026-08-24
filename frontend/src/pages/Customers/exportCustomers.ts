// 목록을 CSV 로 내려받습니다. 화면은 한 장씩만 받아 두므로 내보내기는 따로 전부 모읍니다.
import { client } from '@/api/client'
import type { CustomerContactResponse, PageResponse } from '@/types'
import { downloadCsv, toCsv } from '@/utils/csv'
import { TODAY_ISO } from '@/utils/date'

import type { ColumnDef } from './columns'
import { toCustomer } from './contact'

/** 서버가 한 번에 주는 최대치. 더 크게 요청하면 422 로 돌아옵니다. */
const PAGE = 100

/** 한 번에 모으는 상한. 이보다 많으면 검색으로 좁혀 달라고 말합니다. */
const MAX_ROWS = 5_000

export class TooManyCustomersError extends Error {
  constructor() {
    super(`한 번에 ${MAX_ROWS.toLocaleString()}명까지 내보낼 수 있습니다.`)
    this.name = 'TooManyCustomersError'
  }
}

interface ExportParams {
  /** 화면의 검색어. 보고 있는 목록과 같은 범위를 내보냅니다. */
  query: string
  ownerIds: readonly string[] | undefined
  columns: ColumnDef[]
  signal?: AbortSignal
}

/**
 * 지금 보고 있는 목록을 그대로 파일로 만듭니다. 보이는 컬럼만, 보이는 순서대로 담아
 * 화면과 파일이 어긋나지 않게 합니다.
 */
export async function exportCustomers({ query, ownerIds, columns, signal }: ExportParams) {
  const needle = query.trim()
  const rows: string[][] = []

  for (let skip = 0; ; skip += PAGE) {
    const { data } = await client.get<PageResponse<CustomerContactResponse>>('/customer-contacts', {
      params: {
        q: needle === '' ? undefined : needle.slice(0, 100),
        skip,
        limit: PAGE,
        owner_member_id: ownerIds,
      },
      signal,
    })

    if (data.total > MAX_ROWS) throw new TooManyCustomersError()

    rows.push(
      ...data.items.map(toCustomer).map((customer) => columns.map((c) => c.value(customer))),
    )
    if (!data.has_more) break
  }

  const csv = toCsv(
    columns.map((c) => c.header),
    rows,
  )
  downloadCsv(`고객목록_${TODAY_ISO}.csv`, csv)
  return rows.length
}
