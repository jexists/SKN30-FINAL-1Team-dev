// KPI 타일을 누르면 열리는 목록 두 가지. 둘 다 같은 드로어 한 벌에 담깁니다.
//
// 어느 목록이든 서버가 준 것을 그리기만 합니다. 거르고 정렬하는 일은 카드 숫자를 만든
// 조건과 같아야 해서 서버에 두었습니다. 여기서 다시 거르면 타일과 목록이 어긋납니다.
import { dealDetailPath, ROUTES, supportRequestPath } from '@/constants/routes'
import { STATUS_LABEL as SUPPORT_STATUS_LABEL } from '@/pages/Complaints/statuses'
import { postedLabel, toNotice } from '@/shared/notices'
import type { NoticeResponse, SalesDealResponse, SupportRequestResponse } from '@/types'
import { ddayLabel, fmtDay, parseISO, TODAY } from '@/utils/date'

export type DrawerListTone = 'risk' | 'good' | 'now'

export interface DrawerListRow {
  key: string
  title: string
  titleNote?: string
  /** 제목 옆에 바로 붙는 태그. 아래 태그 줄까지 눈을 내리지 않아도 보이게 합니다. */
  titleTag?: { text: string; tone?: DrawerListTone }
  note?: string
  tags: { text: string; tone?: DrawerListTone }[]
  /** 이 건의 담당자. 여러 사람이 섞여 보일 때만 드로어가 세웁니다. */
  owner?: string
  /** 담당자의 구성원 번호. 이름표에 칠할 색을 찾는 데 씁니다. */
  ownerMemberId?: string
  side: {
    strong?: string
    late?: boolean
    numeric?: boolean
    lines?: { text: string; numeric?: boolean }[]
  }
  /** 있으면 줄이 이 곳으로 넘어가는 링크가 됩니다. */
  href?: string
  orderNo?: string
}

export interface DrawerList {
  title: string
  sub: string
  rows: DrawerListRow[]
  empty?: string
}

export type KpiListKey = 'cs' | 'renewal'

const DAY = 86_400_000
const daysUntil = (dateISO: string) =>
  Math.round((parseISO(dateISO).getTime() - TODAY.getTime()) / DAY)

export function csList(requests: SupportRequestResponse[]): DrawerList {
  // 상태는 접수·원인파악·처리중·처리완료 네 가지입니다. 처리완료가 아니면 아직 남은
  // 건이므로 '미완료' 로 묶어 셉니다. in_progress 만 세면 접수와 원인파악이 완료 쪽으로
  // 넘어가 숫자가 틀립니다.
  const open = requests.filter((request) => request.status_code !== 'completed').length
  const done = requests.length - open
  return {
    title: 'C/S 대응요청',
    sub: `미완료 ${open}건 · 처리완료 ${done}건`,
    rows: [...requests]
      .sort((a, b) => b.occurred_at.localeCompare(a.occurred_at))
      .map((request) => ({
        key: request.id,
        title: request.title,
        titleNote: `${request.customer_company_name} · ${request.contract_no ?? request.deal_no}`,
        owner: request.assignee_display_name,
        ownerMemberId: request.assignee_member_id,
        note: request.body,
        tags: [
          ...(request.is_urgent ? [{ text: '긴급', tone: 'risk' as const }] : []),
          { text: SUPPORT_STATUS_LABEL[request.status_code] },
          { text: fmtDay(new Date(request.occurred_at)) },
        ],
        side: {},
        // 그 자리에서 펼치는 대신 CS 대응 화면의 상세를 엽니다.
        href: supportRequestPath(request.id),
      })),
    empty: '등록된 C/S 대응요청이 없습니다.',
  }
}

export function renewalList(deals: SalesDealResponse[]): DrawerList {
  return {
    title: '계약갱신 예정',
    sub: '계약 종료일 30일 이내',
    rows: deals.map((deal) => {
      // 서버가 종료일 있는 딜만 보내지만 타입에는 남아 있습니다. 없으면 오늘로 읽습니다.
      const endsOn = deal.contract_ends_on
      return {
        key: deal.id,
        title: deal.customer_company_name,
        owner: deal.owner_display_name,
        ownerMemberId: deal.owner_member_id,
        titleTag: {
          text: endsOn ? ddayLabel(daysUntil(endsOn)) : '종료일 미정',
          tone: 'now' as const,
        },
        note: `${deal.deal_no} · ${deal.title}`,
        tags: [],
        side: {},
        // 계약은 딜 한 행에 얹혀 있습니다. 번호로 다시 찾게 하지 않고 그 딜을 바로 엽니다.
        href: dealDetailPath(deal.id),
      }
    }),
    empty: '30일 이내 종료 예정인 계약이 없습니다.',
  }
}

/** 공지·팀장 지시사항 카드의 전체 목록. 제목과 올린 날만 두고, 나머지는 옆 패널에서 봅니다. */
export function noticeList(title: string, notices: NoticeResponse[], total: number): DrawerList {
  return {
    title: `${title} (${total}건)`,
    sub: '',
    rows: notices.map((item) => ({
      key: item.id,
      title: item.title,
      note: postedLabel(toNotice({ ...item, targets: [] })),
      tags: [],
      side: {},
      href: ROUTES.NOTICES,
    })),
  }
}
