// 목록 표의 열입니다. 계약 목록과 같은 배치이고, 계약일 자리에 견적일과 유효기한이
// 들어갑니다. 견적은 기한이 지나면 다시 써야 해서 그 날짜가 표에 있어야 합니다.
import type { DataColumn } from '@/components/DataTable'
import type { Quote } from '@/types'
import { fmtDot, fmtDotShort, parseISO } from '@/utils/date'
import { won } from '@/utils/format'

import { QUOTE_STAGES, stageById } from './stages'

export const QUOTE_COLUMNS: DataColumn<Quote>[] = [
  { id: 'no', header: '견적번호', width: 132, numeric: true, sortable: true, text: (q) => q.no },
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
    text: (q) => fmtDot(parseISO(q.date)),
    sortValue: (q) => q.date,
  },
  {
    id: 'validUntil',
    header: '유효기한',
    width: 124,
    numeric: true,
    sortable: true,
    text: (q) => fmtDotShort(parseISO(q.validUntil)),
    sortValue: (q) => q.validUntil,
  },
  {
    id: 'stage',
    header: '단계',
    width: 112,
    sortable: true,
    text: (q) => stageById(q.stageId)?.name ?? '',
    sortValue: (q) => QUOTE_STAGES.findIndex((stage) => stage.id === q.stageId),
  },
]
