// 고객 API 응답을 화면이 쓰는 모양으로 옮깁니다. 목록·내보내기가 같은 변환을 봅니다.
import type {
  Customer,
  CustomerContactResponse,
  CustomerSource,
  CustomerSourceCode,
  CustomerStatus,
  CustomerStatusCode,
} from '@/types'

// 코드 칸은 서버에서 자유 문자열로 옵니다. 이 앱이 모르는 값이 섞여도 빈칸이 아니라
// '미지정' 으로 보이게 아래 조회에 기본값을 답니다.
const STATUS_LABEL: Record<CustomerStatusCode, CustomerStatus> = {
  new: '신규',
  proposal: '제안',
  negotiation: '협의',
  contracted: '계약',
  on_hold: '보류',
}

export const SOURCE_LABEL: Record<CustomerSourceCode, CustomerSource> = {
  referral: '소개',
  event: '행사·박람회',
  online_form: '온라인 문의',
  joint_past: '기존 거래',
  media: '미디어',
  other: '기타',
}

// 목록 밖의 코드가 오면 화면이 빈칸이 되지 않게 미지정으로 둡니다.
function toSourceLabel(code: string | null): CustomerSource {
  if (code === null) return '미지정'
  return SOURCE_LABEL[code as CustomerSourceCode] ?? '미지정'
}

/** 수정 폼이 되돌려 쓸 코드입니다. 이 앱이 모르는 값은 미지정으로 둡니다. */
function toSourceCode(code: string | null): CustomerSourceCode | null {
  if (code === null) return null
  return code in SOURCE_LABEL ? (code as CustomerSourceCode) : null
}

function toStatusLabel(code: string | null): CustomerStatus {
  if (code === null) return '미지정'
  return STATUS_LABEL[code as CustomerStatusCode] ?? '미지정'
}

export function toCustomer(contact: CustomerContactResponse): Customer {
  return {
    id: contact.id,
    name: contact.name,
    org: contact.company_name,
    dept: contact.department ?? '',
    title: contact.job_title ?? '',
    email: contact.email ?? '',
    phone: contact.phone,
    owner: contact.owner_display_name,
    source: toSourceLabel(contact.source_code),
    sourceCode: toSourceCode(contact.source_code),
    status: toStatusLabel(contact.status_code),
    memo: contact.memo ?? '',
    visited: contact.visited,
    last: null,
    next: null,
    created: contact.registered_at.slice(0, 10),
    overdue: false,
    companyId: contact.company_id,
    ownerMemberId: contact.owner_member_id,
    owners: contact.assignees.map((assignee) => ({
      id: assignee.id,
      name: assignee.display_name,
    })),
    regionCode: contact.company_region_code,
  }
}
