import { useEffect, useState } from 'react'

import { client } from '@/api/client'
import type { CustomerCompanyResponse } from '@/types'

/**
 * 고객이 속한 회사. 사업자 등록번호와 주소는 사람이 아니라 회사에 붙어 있어
 * 고객 목록 응답에는 들어 있지 않습니다.
 *
 * 못 받아 오면 null 입니다. 회사 정보가 없다고 상세를 못 여는 쪽이 더 나쁩니다.
 */
export default function useCustomerCompany(
  companyId: string | undefined,
): CustomerCompanyResponse | null {
  const [company, setCompany] = useState<CustomerCompanyResponse | null>(null)

  useEffect(() => {
    setCompany(null)
    if (companyId === undefined) return
    const controller = new AbortController()
    void client
      .get<CustomerCompanyResponse>(`/customer-companies/${companyId}`, {
        signal: controller.signal,
      })
      .then(({ data }) => {
        if (!controller.signal.aborted) setCompany(data)
      })
      .catch(() => {
        // 사업자번호·주소만 비고 나머지 상세는 그대로 열립니다.
      })

    return () => controller.abort()
  }, [companyId])

  return company
}
