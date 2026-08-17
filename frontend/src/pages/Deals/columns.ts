// 목록 표의 열입니다. 무엇을 보여 주고 무엇으로 정렬하는지를 한 곳에 모읍니다.
//
// 단계 열만 보이는 값과 정렬 기준이 다릅니다. 이름순으로 세우면 '검토 → 확정'
// 같은 진행 순서가 흐트러져 보드 컬럼 순서를 그대로 씁니다.
import type { DataColumn } from '@/components/DataTable'
import { fmtDot, parseISO } from '@/utils/date'
import { won } from '@/utils/format'

import type { BoardColumn, BoardDeal } from './board'

/** 단계까지 봐야 정렬 순서를 알 수 있어 컬럼 목록을 받아 만듭니다. */
export function dealColumns(stages: BoardColumn[]): DataColumn<BoardDeal>[] {
  return [
    { id: 'no', header: '영업번호', width: 132, numeric: true, sortable: true, text: (c) => c.no },
    { id: 'org', header: '고객사', width: 172, sortable: true, text: (c) => c.org },
    { id: 'product', header: '제품', width: 156, sortable: true, text: (c) => c.product },
    { id: 'kind', header: '유형', width: 96, sortable: true, text: (c) => c.kind },
    {
      id: 'pipeline',
      header: '파이프라인',
      width: 120,
      sortable: true,
      text: (c) => ('pipelineName' in c ? String(c.pipelineName) : ''),
    },
    {
      id: 'amount',
      header: '금액',
      width: 112,
      align: 'right',
      numeric: true,
      sortable: true,
      text: (c) => won(c.amount),
      sortValue: (c) => c.amount,
    },
    { id: 'owner', header: '담당 영업', width: 96, sortable: true, text: (c) => c.owner },
    {
      id: 'date',
      header: '영업 시작일',
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
      // '제품 시연 평가' 배지가 그대로 들어가야 해서 다른 열보다 넓습니다.
      width: 132,
      sortable: true,
      text: (c) =>
        stages.find((col) => col.id === c.stageId)?.name ??
        ('stageName' in c ? String(c.stageName) : ''),
      sortValue: (c) =>
        'stageOrder' in c
          ? `${'pipelineName' in c ? String(c.pipelineName) : ''}\0${String(c.stageOrder).padStart(10, '0')}`
          : stages.findIndex((col) => col.id === c.stageId),
    },
  ]
}
