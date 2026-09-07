// 고른 줄을 CSV 로 내려받습니다. 표에 이미 있는 값만 쓰므로 서버에 다시 묻지 않습니다.
import type { Customer } from '@/types'
import { downloadCsv, toCsv } from '@/utils/csv'
import { TODAY_ISO } from '@/utils/date'

import type { ColumnDef } from './columns'

interface ExportParams {
  /** 내보낼 고객. 표에서 체크한 줄만 넘어옵니다. */
  customers: readonly Customer[]
  columns: ColumnDef[]
}

/**
 * 고른 고객을 그대로 파일로 만듭니다. 보이는 컬럼만, 보이는 순서대로 담아
 * 화면과 파일이 어긋나지 않게 합니다.
 */
export function exportCustomers({ customers, columns }: ExportParams) {
  const csv = toCsv(
    columns.map((c) => c.header),
    customers.map((customer) => columns.map((c) => c.value(customer))),
  )
  downloadCsv(`고객목록_${TODAY_ISO}.csv`, csv)
  return customers.length
}
