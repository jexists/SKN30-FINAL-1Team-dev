// 엑셀로 여러 고객을 넣을 때 쓰는 열 이름, 템플릿, 결과 문구입니다.
import type { CustomerContactBulkItem } from '@/types'

/** CSV 헤더 ↔ 고객 등록 폼의 칸. 내보내기가 쓰는 이름과 같아 왕복이 됩니다. */
export const HEADER_MAP = {
  회사: 'org',
  '사업자 등록번호': 'businessNo',
  이름: 'name',
  전화: 'phone',
  부서: 'dept',
  직함: 'title',
  이메일: 'email',
  방문여부: 'visited',
  메모: 'memo',
} as const

export type Header = keyof typeof HEADER_MAP
export type Field = (typeof HEADER_MAP)[Header]

export const HEADERS = Object.keys(HEADER_MAP) as Header[]

/** 없으면 한 줄도 읽을 수 없는 열입니다. */
export const REQUIRED: Record<'name' | 'org' | 'phone', string> = {
  name: '이름',
  org: '회사',
  phone: '전화',
}

/** 읽어 낸 한 줄을 일괄 등록 API 가 받는 모양으로 바꿉니다. */
export function toBulkItem(row: number, values: Record<Field, string>): CustomerContactBulkItem {
  return {
    row,
    company_name: values.org,
    business_no: values.businessNo,
    name: values.name,
    department: values.dept,
    job_title: values.title,
    email: values.email,
    phone: values.phone,
    visited: values.visited,
    memo: values.memo,
  }
}

/** 서버가 한 번에 받는 최대 줄 수. 백엔드의 BULK_MAX_ROWS 와 같은 값입니다. */
export const MAX_ROWS = 1_000
