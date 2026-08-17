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
  { id: 'org', header: '고객사', width: 160, sortable: true, text: (q) => q.org },
  { id: 'product', header: '제품', width: 150, sortable: true, text: (q) => q.product },
  { id: 'kind', header: '유형', width: 92, sortable: true, text: (q) => q.kind },
  {
    id: 'amount',
    header: '금액',
    width: 112,
    align: 'right',
    numeric: true,
    sortable: true,
    text: (q) => won(q.amount),
    sortValue: (q) => q.amount,
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
    header: '단계',
    width: 112,
    sortable: true,
    text: (q) => q.stageName,
    sortValue: (q) => q.stageOrder,
  },
]
