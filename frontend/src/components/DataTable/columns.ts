// 표의 열 정의와 정렬 규칙입니다. DataTable.tsx 에서 떼어 둔 이유는 컴포넌트 파일이
// 컴포넌트만 내보내야 개발 중 빠른 갱신(fast refresh)이 살아 있기 때문입니다.

export interface DataColumn<T> {
  id: string
  header: string
  width: number
  /** 금액처럼 오른쪽에 붙는 열 */
  align?: 'right'
  /** 자릿수를 맞출 열(tnum) */
  numeric?: boolean
  sortable?: boolean
  /** 셀에 찍을 글자. 배지처럼 모양이 있는 칸은 renderCell 이 대신 그립니다. */
  text: (row: T) => string
  /** 정렬 기준. 없으면 text 를 씁니다. */
  sortValue?: (row: T) => string | number
}

/** 지금 어느 열로 세워 두었는지. null 이면 원래 순서입니다. */
export type SortState = { id: string; dir: 'asc' | 'desc' } | null

/** 한 열을 기준으로 세우는 비교 함수. 숫자는 크기로, 글자는 한국어 순서로 봅니다. */
export function compareBy<T>(columns: DataColumn<T>[], columnId: string) {
  const column = columns.find((col) => col.id === columnId)
  const of = (row: T) => (column?.sortValue ? column.sortValue(row) : (column?.text(row) ?? ''))

  return (a: T, b: T) => {
    const left = of(a)
    const right = of(b)
    if (typeof left === 'number' && typeof right === 'number') return left - right
    return String(left).localeCompare(String(right), 'ko')
  }
}
