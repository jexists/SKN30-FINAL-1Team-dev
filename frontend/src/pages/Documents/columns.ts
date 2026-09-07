// 목록 표의 열입니다. 무엇을 보여 주고 무엇으로 정렬하는지를 한 곳에 모읍니다.
// 발주 목록의 columns.ts 와 같은 구조입니다.
//
// 분류 열은 보이는 값과 정렬 기준이 다릅니다. 이름순으로 세우면 '계약서 → 기타'
// 같은 탭 순서가 흐트러져 DOCUMENT_CATEGORIES 의 순서를 그대로 씁니다.
import type { SalesDocument } from '@/types'
import { sizeLabel } from '@/utils/attachment'
import { fmtDotShort, parseISO } from '@/utils/date'

import { DOCUMENT_CATEGORIES, fileOf } from './catalog'

export interface DocumentColumn {
  id: string
  header: string
  width: number
  /** 크기처럼 오른쪽에 붙는 열 */
  align?: 'right'
  /** 자릿수를 맞출 열(tnum) */
  numeric?: boolean
  sortable?: boolean
  /** 셀에 찍을 글자. 파일명·분류는 표에서 따로 그립니다. */
  text: (doc: SalesDocument) => string
  /** 정렬 기준. 없으면 text 를 씁니다. */
  sortValue?: (doc: SalesDocument) => string | number
}

/** 연결 대상 한 줄. 붙은 데가 없으면 빈 칸으로 둡니다. */
export const linkLabel = (doc: SalesDocument) =>
  doc.link.kind === 'none' ? '' : `${doc.link.kind} · ${doc.link.label}`

export const DOCUMENT_COLUMNS: DocumentColumn[] = [
  { id: 'title', header: '파일명', width: 300, sortable: true, text: (d) => d.title },
  {
    id: 'category',
    header: '분류',
    width: 116,
    sortable: true,
    text: (d) => d.category,
    sortValue: (d) => DOCUMENT_CATEGORIES.indexOf(d.category),
  },
  { id: 'link', header: '연결', width: 190, sortable: true, text: linkLabel },
  {
    id: 'size',
    header: '크기',
    width: 92,
    align: 'right',
    numeric: true,
    sortable: true,
    text: (d) => sizeLabel(fileOf(d).bytes),
    sortValue: (d) => fileOf(d).bytes,
  },
  { id: 'owner', header: '등록자', width: 96, sortable: true, text: (d) => fileOf(d).owner },
  {
    id: 'uploaded',
    header: '등록일',
    width: 96,
    numeric: true,
    sortable: true,
    text: (d) => fmtDotShort(parseISO(fileOf(d).uploaded)),
    sortValue: (d) => fileOf(d).uploaded,
  },
  // 상세를 열지 않고 파일을 바로 받는 칸입니다. 표에서 버튼으로 그립니다.
  { id: 'download', header: '받기', width: 68, align: 'right', text: () => '' },
]

/** 지금 어느 열로 세워 두었는지. null 이면 원래 순서입니다. */
export type SortState = { id: string; dir: 'asc' | 'desc' } | null

const COLUMN_BY_ID = new Map(DOCUMENT_COLUMNS.map((col) => [col.id, col]))

/** 한 열을 기준으로 세우는 비교 함수. 숫자는 크기로, 글자는 한국어 순서로 봅니다. */
export function compareBy(columnId: string) {
  const column = COLUMN_BY_ID.get(columnId)
  const of = (doc: SalesDocument) =>
    column?.sortValue ? column.sortValue(doc) : (column?.text(doc) ?? '')

  return (a: SalesDocument, b: SalesDocument) => {
    const left = of(a)
    const right = of(b)
    if (typeof left === 'number' && typeof right === 'number') return left - right
    return String(left).localeCompare(String(right), 'ko')
  }
}
