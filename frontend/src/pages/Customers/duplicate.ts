import type { CustomerDuplicateResponse } from '@/types'

/** 지금 등록하려던 값. 폼과 명함·등록증 흐름이 모두 이 모양으로 넘깁니다. */
export interface DuplicateDraft {
  companyName: string
  name: string
  department: string
  jobTitle: string
  email: string
  phone: string
  memo: string
  visited: boolean
}

const text = (value: string | null): string => (value ?? '').trim()

/**
 * 기존 고객을 고쳐야 할 것이 있는지. 없으면 물어볼 것도 없으므로 화면은 이미 등록된
 * 고객이라고만 알립니다.
 *
 * 회사는 비교하지 않습니다 — 회사가 다른데도 같은 사람으로 본 경우는 전화나 이메일이
 * 겹친 것이고, 그 사람을 다른 회사로 옮길지는 고객 수정에서 사람이 정합니다.
 */
export function isSameCustomer(draft: DuplicateDraft, match: CustomerDuplicateResponse): boolean {
  return (
    draft.name.trim() === match.name.trim() &&
    draft.department.trim() === text(match.department) &&
    draft.jobTitle.trim() === text(match.job_title) &&
    draft.email.trim() === text(match.email) &&
    draft.phone.trim() === match.phone.trim() &&
    draft.memo.trim() === text(match.memo) &&
    draft.visited === match.visited
  )
}
