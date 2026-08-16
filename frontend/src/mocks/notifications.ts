// 헤더 벨에 걸리는 한 줄 알림. 시연용 합성 데이터입니다.
//
// to 는 어느 프로필로 로그인해도 열리는 목록 화면만 씁니다. 상세 경로는 담당자
// 스코프에 걸려 "찾을 수 없음" 이 뜰 수 있어 넣지 않았습니다.
import { ROUTES } from '@/constants/routes'
import type { AppNotification } from '@/types'

export const notifications: AppNotification[] = [
  {
    id: 'n1',
    text: '긴급 C/S 1건이 접수되었습니다. 오늘 중 1차 응답이 필요합니다.',
    postedOff: 0,
    postedAt: '08:05',
    read: false,
    to: ROUTES.COMPLAINTS,
  },
  {
    id: 'n2',
    text: '김서현 팀장이 지시사항을 올렸습니다. 갱신 예정 계약 2건 확인 요청.',
    postedOff: 0,
    postedAt: '09:10',
    read: false,
    to: ROUTES.CONTRACTS,
  },
  {
    id: 'n3',
    text: '오늘 미팅 일정이 3건 있습니다.',
    postedOff: 0,
    postedAt: '07:30',
    read: false,
    to: ROUTES.CALENDAR,
  },
  {
    id: 'n4',
    text: '어제 업무보고가 아직 제출되지 않았습니다.',
    postedOff: -1,
    postedAt: '18:00',
    read: true,
    to: ROUTES.DAILY,
  },
  {
    id: 'n5',
    text: 'CardioView X7 8월 프로모션 단가표가 갱신되었습니다.',
    postedOff: -1,
    postedAt: '17:20',
    read: true,
    to: ROUTES.QUOTES,
  },
  {
    id: 'n6',
    text: '발주 1건의 납기가 다음 주로 다가왔습니다.',
    postedOff: -2,
    postedAt: '11:40',
    read: true,
    to: ROUTES.ORDERS,
  },
]
