import type { CustomerContactResponse } from '@/types'

/** 고른 담당자. 회사·부서·직함은 고르고 나면 딸려 오는 값이라 함께 담습니다. */
export interface ContactOption {
  id: string
  name: string
  companyId: string
  org: string
  dept: string
  title: string
}

export function toContactOption(contact: CustomerContactResponse): ContactOption {
  return {
    id: contact.id,
    name: contact.name,
    companyId: contact.company_id,
    org: contact.company_name,
    dept: contact.department ?? '',
    title: contact.job_title ?? '',
  }
}
