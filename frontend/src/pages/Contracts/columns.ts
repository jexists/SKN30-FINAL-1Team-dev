// 계약 목록 표의 열입니다.
//
// 금액은 deal_amount 가 아니라 contract_amount 를 봅니다. 견적가에서 협의로 깎인 값이
// 여기에 남고, 견적가·영업 예상금액은 같은 행에 그대로 있습니다.
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
  { id: 'title', header: '딜 제목', width: 180, sortable: true, text: (c) => c.title },
  { id: 'org', header: '고객사', width: 160, sortable: true, text: (c) => c.org },
  { id: 'product', header: '제품', width: 140, sortable: true, text: (c) => c.product },
  {
    id: 'amount',
    header: '계약금액',
    width: 116,
    align: 'right',
    numeric: true,
    sortable: true,
    text: (c) => (c.contractAmount === null ? '-' : won(c.contractAmount)),
    sortValue: (c) => c.contractAmount ?? 0,
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
    id: 'endsOn',
    header: '계약 종료일',
    width: 112,
    numeric: true,
    sortable: true,
    text: (c) => (c.contractEndsOn ? fmtDot(parseISO(c.contractEndsOn)) : '-'),
    sortValue: (c) => c.contractEndsOn ?? '',
  },
  {
    id: 'stage',
    header: '계약상태',
    width: 112,
    sortable: true,
    text: (c) => c.contractStatusName ?? '-',
    sortValue: (c) => c.contractStatusName ?? '',
  },
]
