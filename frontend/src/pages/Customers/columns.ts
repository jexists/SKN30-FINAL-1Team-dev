// 컬럼을 배열로 선언해 두면 표시·정렬·검색·CSV 가 같은 정의를 봅니다.
// 셋을 따로 두면 컬럼을 하나 늘릴 때 세 군데를 고쳐야 하고 결국 어긋납니다.
import { createElement, type ReactNode } from 'react'

import type { Customer } from '@/types'
import { fmtDotShort, parseISO } from '@/utils/date'

import { EmailCell, OwnerCell, PlainNumber, VisitCell } from './cells'

export interface ColumnDef {
  id: string
  header: string
  /** 기본 폭(px). 표 헤더 경계를 끌면 덮어씁니다. */
  width: number
  minWidth: number
  sortable: boolean
  /** 첫 열은 숨길 수 없고 가로 스크롤에도 왼쪽에 고정됩니다. */
  fixed?: boolean
  /** 정렬·검색·CSV 가 쓰는 평문 값 */
  value: (c: Customer) => string
  /** 표시 전용. 없으면 value 를 그대로 씁니다. */
  render?: (c: Customer) => ReactNode
}

const short = (isoDate: string) => fmtDotShort(parseISO(isoDate))

/** 담당자 이름. API 응답에 담당자 목록이 없으면 대표 한 명만 씁니다. */
const ownerNames = (c: Customer): string[] =>
  c.owners !== undefined && c.owners.length > 0 ? c.owners.map((o) => o.name) : [c.owner]

export const ALL_COLUMNS: ColumnDef[] = [
  {
    id: 'org',
    header: '회사',
    width: 150,
    minWidth: 110,
    sortable: true,
    fixed: true,
    value: (c) => c.org,
  },
  {
    id: 'name',
    header: '이름',
    width: 110,
    minWidth: 88,
    sortable: true,
    fixed: true,
    value: (c) => c.name,
  },
  {
    id: 'dept',
    header: '부서',
    width: 140,
    minWidth: 100,
    sortable: true,
    value: (c) => c.dept,
  },
  {
    id: 'title',
    header: '직함',
    width: 92,
    minWidth: 76,
    sortable: true,
    value: (c) => c.title,
  },
  {
    id: 'email',
    header: '이메일',
    width: 190,
    minWidth: 140,
    sortable: true,
    value: (c) => c.email,
    render: (c) => createElement(EmailCell, { email: c.email }),
  },
  {
    id: 'phone',
    header: '전화',
    width: 128,
    minWidth: 120,
    sortable: false,
    value: (c) => c.phone,
    render: (c) => createElement(PlainNumber, { value: c.phone }),
  },
  {
    id: 'owner',
    header: '담당자',
    width: 110,
    minWidth: 90,
    sortable: true,
    // 정렬·검색·CSV 는 담당자 전체를 봅니다. 표에만 대표 한 명과 +N 으로 줄여 놓습니다.
    value: (c) => ownerNames(c).join(', '),
    render: (c) => createElement(OwnerCell, { names: ownerNames(c) }),
  },
  {
    id: 'visited',
    header: '방문여부',
    width: 96,
    minWidth: 82,
    sortable: false,
    // CSV 도 같은 말을 씁니다. 내보낸 파일을 그대로 다시 가져올 수 있어야 합니다.
    value: (c) => (c.visited ? '방문' : '미방문'),
    render: (c) => createElement(VisitCell, { visited: c.visited }),
  },
  {
    id: 'created',
    header: '등록일',
    width: 150,
    minWidth: 130,
    sortable: true,
    value: (c) => short(c.created),
    render: (c) => createElement(PlainNumber, { value: short(c.created) }),
  },
  {
    id: 'memo',
    header: '메모',
    width: 260,
    minWidth: 160,
    sortable: false,
    value: (c) => c.memo,
  },
]

/** 처음 보이는 컬럼. 나머지는 컬럼 설정에서 켭니다. */
// 고객 등록 모달에서 받는 항목과 같은 순서로 둡니다.
export const DEFAULT_VISIBLE = [
  'org',
  'name',
  'dept',
  'title',
  'email',
  'phone',
  'owner',
  'visited',
  'memo',
]

export const COLUMN_BY_ID = new Map(ALL_COLUMNS.map((c) => [c.id, c]))
