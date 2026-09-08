// 목록 표의 열입니다. 무엇을 보여 주고 무엇으로 정렬하는지를 한 곳에 모읍니다.
//
// 단계 열만 보이는 값과 정렬 기준이 다릅니다. 이름순으로 세우면 '검토 → 확정'
// 같은 진행 순서가 흐트러져 보드 컬럼 순서를 그대로 씁니다.
import type { DataColumn } from '@/components/DataTable'
import { fmtDot, parseISO } from '@/utils/date'
import { won } from '@/utils/format'

import type { BoardColumn } from './board'
import type { SalesDeal } from './useSalesDeals'

/** 단계까지 봐야 정렬 순서를 알 수 있어 컬럼 목록을 받아 만듭니다. */
export function dealColumns(stages: BoardColumn[]): DataColumn<SalesDeal>[] {
  return [
    { id: 'no', header: '영업번호', width: 132, numeric: true, sortable: true, text: (c) => c.no },
    { id: 'org', header: '고객사', width: 172, sortable: true, text: (c) => c.org },
    { id: 'product', header: '제품', width: 156, sortable: true, text: (c) => c.product },
    {
      id: 'amount',
      // 견적가·계약가가 아니라 딜을 열 때 적은 예상금액입니다.
      header: '예상금액',
      width: 112,
      align: 'right',
      numeric: true,
      sortable: true,
      text: (c) => won(c.amount),
      sortValue: (c) => c.amount,
    },
    { id: 'owner', header: '담당 영업', width: 96, sortable: true, text: (c) => c.owner },
    {
      id: 'stage',
      header: '단계',
      // '제품 시연 평가' 배지가 그대로 들어가야 해서 다른 열보다 넓습니다.
      width: 132,
      sortable: true,
      text: (c) => stages.find((col) => col.id === c.stageId)?.name ?? c.stageName,
      sortValue: (c) => `${c.pipelineName}\0${String(c.stageOrder).padStart(10, '0')}`,
    },
    {
      id: 'updated',
      // 언제 시작했는지보다 마지막으로 움직인 때가 목록에서 쓸모 있습니다. 서버도
      // 이 순서로 세워 보냅니다.
      header: '최근 수정',
      width: 108,
      numeric: true,
      sortable: true,
      // 서울 시각의 ISO datetime 이라 날짜만 잘라 넘깁니다. 정렬은 문자열 그대로가
      // 곧 시각순입니다.
      text: (c) => fmtDot(parseISO(c.updatedAt.slice(0, 10))),
      sortValue: (c) => c.updatedAt,
    },
  ]
}
