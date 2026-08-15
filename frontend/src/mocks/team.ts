// 영업팀 명부. 시연용 합성 데이터입니다.
//
// 담당자 이름은 화면마다 흩어진 owner 문자열(고객·계약·발주·자료실)과 같은 값이라야
// 스코프가 맞습니다. 백엔드가 붙으면 REP 테이블이 이 자리를 대신하고, id 가 rep_id 가
// 됩니다. 지금은 이름이 사실상의 키라 name 을 바꾸면 시드 데이터도 함께 바꿔야 합니다.
import type { TeamMember } from '@/types'

export const TEAM: TeamMember[] = [
  {
    id: 'rep-1',
    name: '김서현',
    title: '영업팀장',
    role: 'manager',
    active: true,
    monthlyTarget: 0,
  },
  {
    id: 'rep-2',
    name: '김지훈',
    title: '영업 담당자',
    role: 'member',
    active: true,
    monthlyTarget: 100_000_000,
  },
  {
    id: 'rep-3',
    name: '이수민',
    title: '영업 담당자',
    role: 'member',
    active: true,
    monthlyTarget: 80_000_000,
  },
  {
    id: 'rep-4',
    name: '박도윤',
    title: '영업 담당자',
    role: 'member',
    active: true,
    monthlyTarget: 70_000_000,
  },
  {
    id: 'rep-5',
    name: '최가은',
    title: '영업 담당자',
    role: 'member',
    active: true,
    monthlyTarget: 50_000_000,
  },
]
