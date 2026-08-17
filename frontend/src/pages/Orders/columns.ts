// 목록 표의 열입니다. 무엇을 보여 주고 무엇으로 정렬하는지를 한 곳에 모읍니다.
//
// 상태 열만 보이는 값과 정렬 기준이 다릅니다. 이름순으로 세우면 '발주 접수 → 납품 완료'
// 같은 진행 순서가 흐트러져 ORDER_STATUSES 의 순서를 그대로 씁니다.
import type { DataColumn } from '@/components/DataTable'
import { orderItemLabel, orderTotal } from '@/shared/orders'
import type { ApiPurchaseOrder } from '@/types'
import { fmtDotShort, parseISO } from '@/utils/date'
import { won } from '@/utils/format'

import { ORDER_STATUSES } from './pipeline'

export const ORDER_COLUMNS: DataColumn<ApiPurchaseOrder>[] = [
  { id: 'no', header: '발주번호', width: 132, numeric: true, sortable: true, text: (o) => o.no },
  { id: 'hospital', header: '고객사', width: 140, sortable: true, text: (o) => o.hospital },
  { id: 'items', header: '품목', width: 160, sortable: true, text: orderItemLabel },
  { id: 'supplier', header: '공급처', width: 124, sortable: true, text: (o) => o.supplier },
  {
    id: 'owner',
    header: '담당 영업',
    width: 96,
    sortable: true,
    text: (o) => o.owner,
  },
  {
    id: 'amount',
    header: '금액',
    width: 110,
    align: 'right',
    numeric: true,
    sortable: true,
    text: (o) => won(orderTotal(o)),
    sortValue: orderTotal,
  },
  // 날짜 두 열은 정렬 기준이 ISO 문자열 그대로가 곧 날짜순입니다.
  // 예상 입고는 표에 두지 않습니다. 납기와 나란히 두면 폭만 먹고, 늦은 건은
  // 납기 칸에 지연 일수가 함께 나오므로 훑어볼 때 아쉬울 것이 없습니다.
  {
    id: 'ordered',
    header: '발주일',
    width: 96,
    numeric: true,
    sortable: true,
    text: (o) => fmtDotShort(parseISO(o.ordered)),
    sortValue: (o) => o.ordered,
  },
  {
    id: 'due',
    header: '납기',
    width: 132,
    numeric: true,
    sortable: true,
    text: (o) => fmtDotShort(parseISO(o.due)),
    sortValue: (o) => o.due,
  },
  {
    id: 'status',
    // '출고 의뢰서 완료' 배지가 그대로 들어가야 해서 다른 열보다 넓습니다.
    header: '상태',
    width: 140,
    sortable: true,
    text: (o) => o.status,
    sortValue: (o) => ORDER_STATUSES.indexOf(o.status),
  },
]
