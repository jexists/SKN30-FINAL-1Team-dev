import { useEffect, useState } from 'react'

import { client } from '@/api/client'
import type { CustomerAttachment } from '@/types'

/**
 * 고객 등록에 쓴 명함·사업자등록증 원본. 저장소 주소는 서버가 내보내지 않으므로
 * 서명 주소를 건별로 받아 옵니다.
 *
 * 주소는 5분이면 만료합니다. 상세를 오래 열어 두면 사진 자리가 비고,
 * 그때는 다시 열면 됩니다.
 */
export default function useCustomerAttachments(contactId: string): CustomerAttachment[] {
  const [attachments, setAttachments] = useState<CustomerAttachment[]>([])

  useEffect(() => {
    setAttachments([])
    const controller = new AbortController()
    void client
      .get<CustomerAttachment[]>(`/customer-contacts/${contactId}/attachments`, {
        signal: controller.signal,
      })
      .then(({ data }) => {
        if (!controller.signal.aborted) setAttachments(data)
      })
      .catch(() => {
        // 첨부를 못 받았다고 상세 전체가 실패하지는 않습니다. 없는 것으로 둡니다.
      })

    return () => controller.abort()
  }, [contactId])

  return attachments
}
