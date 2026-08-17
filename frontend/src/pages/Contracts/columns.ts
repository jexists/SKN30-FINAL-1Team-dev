import type { DataColumn } from '@/components/DataTable'
import type { SalesDeal } from '@/pages/Deals/useSalesDeals'
import { fmtDot, parseISO } from '@/utils/date'
import { won } from '@/utils/format'

export const CONTRACT_COLUMNS: DataColumn<SalesDeal>[] = [
  {
    id: 'no',
    header: '계약번호',
    width: 132,
    numeric: true,
    sortable: true,
    text: (c) => c.contractNo ?? c.no,
  },
  { id: 'org', header: '고객사', width: 180, sortable: true, text: (c) => c.org },
  { id: 'product', header: '제품', width: 160, sortable: true, text: (c) => c.product },
  { id: 'kind', header: '유형', width: 96, sortable: true, text: (c) => c.kind },
  {
    id: 'amount',
    header: '금액',
    width: 116,
    align: 'right',
    numeric: true,
    sortable: true,
    text: (c) => won(c.amount),
    sortValue: (c) => c.amount,
  },
  { id: 'owner', header: '담당 영업', width: 96, sortable: true, text: (c) => c.owner },
  {
    id: 'date',
    header: '계약일',
    width: 108,
    numeric: true,
    sortable: true,
    // 정렬은 ISO 문자열 그대로가 곧 날짜순입니다.
    text: (c) => (c.contractSignedOn ? fmtDot(parseISO(c.contractSignedOn)) : '-'),
    sortValue: (c) => c.contractSignedOn ?? '',
  },
  {
    id: 'stage',
    header: '단계',
    width: 112,
    sortable: true,
    text: (c) => c.stageName,
    sortValue: (c) => c.stageOrder,
  },
]
