// 견적 목록 표의 열입니다.
//
// 금액은 deal_amount 가 아니라 quote_amount 를 봅니다. 셋(영업·견적·계약)이 한 행에
// 나란히 남아야 계약으로 넘어간 뒤에도 견적가가 그대로 보입니다.
import type { DataColumn } from '@/components/DataTable'
import type { SalesDeal } from '@/pages/Deals/useSalesDeals'
import { fmtDot, fmtDotShort, parseISO } from '@/utils/date'
import { won } from '@/utils/format'

export const QUOTE_COLUMNS: DataColumn<SalesDeal>[] = [
  {
    id: 'no',
    header: '견적번호',
    width: 132,
    numeric: true,
    sortable: true,
    text: (q) => q.quoteNo ?? q.no,
  },
  { id: 'title', header: '딜 제목', width: 180, sortable: true, text: (q) => q.title },
  { id: 'org', header: '고객사', width: 150, sortable: true, text: (q) => q.org },
  {
    id: 'issuer',
    header: '견적업체명',
    width: 132,
    sortable: true,
    text: (q) => q.teamCompanyName ?? '-',
  },
  {
    id: 'amount',
    header: '견적금액',
    width: 116,
    align: 'right',
    numeric: true,
    sortable: true,
    text: (q) => (q.quoteAmount === null ? '-' : won(q.quoteAmount)),
    sortValue: (q) => q.quoteAmount ?? 0,
  },
  {
    id: 'delivery',
    header: '납품예상일자',
    width: 150,
    sortable: true,
    text: (q) => q.quoteDeliveryTerms ?? '-',
  },
  { id: 'owner', header: '담당 영업', width: 92, sortable: true, text: (q) => q.owner },
  {
    id: 'date',
    header: '견적일',
    width: 104,
    numeric: true,
    sortable: true,
    // 정렬은 ISO 문자열 그대로가 곧 날짜순입니다.
    text: (q) => (q.quoteIssuedOn ? fmtDot(parseISO(q.quoteIssuedOn)) : '-'),
    sortValue: (q) => q.quoteIssuedOn ?? '',
  },
  {
    id: 'validUntil',
    header: '유효기한',
    width: 124,
    numeric: true,
    sortable: true,
    text: (q) => (q.quoteValidUntil ? fmtDotShort(parseISO(q.quoteValidUntil)) : '-'),
    sortValue: (q) => q.quoteValidUntil ?? '',
  },
  {
    id: 'stage',
    header: '견적상태',
    width: 112,
    sortable: true,
    text: (q) => q.quoteStatusName ?? '-',
    sortValue: (q) => q.quoteStatusName ?? '',
  },
]
