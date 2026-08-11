// 컬럼을 배열로 선언해 두면 표시·정렬·검색·CSV 가 같은 정의를 봅니다.
// 셋을 따로 두면 컬럼을 하나 늘릴 때 세 군데를 고쳐야 하고 결국 어긋납니다.
import { createElement, type ReactNode } from 'react'

import type { Customer } from '@/content/types'
import { fmtDotShort, parseISO } from '@/utils/date'

import { DateCell, EmailCell, NameCell, NextCell, PlainNumber, StatusCell } from './cells'

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

export const ALL_COLUMNS: ColumnDef[] = [
  {
    id: 'name',
    header: '이름',
    width: 170,
    minWidth: 140,
    sortable: true,
    fixed: true,
    value: (c) => c.name,
    render: (c) => createElement(NameCell, { customer: c }),
  },
  {
    id: 'org',
    header: '회사',
    width: 150,
    minWidth: 110,
    sortable: true,
    value: (c) => c.org,
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
    header: '담당 영업',
    width: 110,
    minWidth: 90,
    sortable: true,
    value: (c) => c.owner,
  },
  {
    id: 'source',
    header: '유입 소스',
    width: 110,
    minWidth: 90,
    sortable: true,
    value: (c) => c.source,
  },
  {
    id: 'status',
    header: '상태',
    width: 88,
    minWidth: 82,
    sortable: true,
    value: (c) => c.status,
    render: (c) => createElement(StatusCell, { customer: c }),
  },
  {
    id: 'last',
    header: '최근 접촉',
    width: 132,
    minWidth: 124,
    sortable: true,
    value: (c) => short(c.last),
    render: (c) => createElement(DateCell, { date: c.last }),
  },
  {
    id: 'next',
    header: '다음 일정',
    width: 152,
    minWidth: 140,
    sortable: true,
    // 미등록은 빈 값이라 오름차순에서 맨 위로 옵니다. 후속이 늦은 쪽을 먼저 보는 게 맞습니다.
    value: (c) => (c.next === null ? '' : short(c.next)),
    render: (c) => createElement(NextCell, { customer: c }),
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
export const DEFAULT_VISIBLE = ['name', 'org', 'title', 'email', 'phone', 'status', 'last', 'next']

export const COLUMN_BY_ID = new Map(ALL_COLUMNS.map((c) => [c.id, c]))
