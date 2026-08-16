// 목록 표의 열입니다. 무엇을 보여 주고 무엇으로 정렬하는지를 한 곳에 모읍니다.
//
// 단계 열만 보이는 값과 정렬 기준이 다릅니다. 이름순으로 세우면 '초안작성 → 계약완료'
// 같은 진행 순서가 흐트러져 CONTRACT_STAGES 의 순서를 그대로 씁니다.
import type { DataColumn } from '@/components/DataTable'
import type { StagedContract } from '@/types'
import { fmtDot, parseISO } from '@/utils/date'
import { won } from '@/utils/format'

import { CONTRACT_STAGES, stageById } from './stages'

export const CONTRACT_COLUMNS: DataColumn<StagedContract>[] = [
  { id: 'no', header: '계약번호', width: 132, numeric: true, sortable: true, text: (c) => c.no },
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
    text: (c) => fmtDot(parseISO(c.date)),
    sortValue: (c) => c.date,
  },
  {
    id: 'stage',
    header: '단계',
    width: 112,
    sortable: true,
    text: (c) => stageById(c.stageId)?.name ?? '',
    sortValue: (c) => CONTRACT_STAGES.findIndex((stage) => stage.id === c.stageId),
  },
]
