// 로그인 화면이 고르는 데모 프로필입니다. 실제 인증이 붙으면 이 파일과 함께 사라집니다.
import type { Role } from '@/types'

export interface MockProfile {
  id: string
  /** 로그인 버튼에 찍히는 이름 */
  label: string
  note: string
  role: Role
  /** 화면 우상단에 뜨는 사용자 */
  name: string
  title: string
  /**
   * 이 프로필이 보는 담당자. null 이면 팀 전체입니다.
   * 스코프가 닿지 않는 시드(일정·후속·보고서·추천)를 이 값으로 거릅니다.
   */
  owner: string | null
  /** 영업 데이터를 채울지. false 면 계정만 있고 데이터는 없는 첫 세팅입니다. */
  seeded: boolean
}

export const MOCK_PROFILES: MockProfile[] = [
  {
    id: 'sample-member',
    label: '샘플 · 영업 담당자',
    note: '김지훈의 고객·일정·문서',
    role: 'member',
    name: '김지훈',
    title: '영업 담당자',
    owner: '김지훈',
    seeded: true,
  },
  {
    id: 'sample-manager',
    label: '샘플 · 영업 팀장',
    note: '팀 전체 현황과 매출',
    role: 'manager',
    name: '김서현',
    title: '영업팀장',
    owner: null,
    seeded: true,
  },
  {
    id: 'empty-member',
    label: '첫 세팅 · 영업 담당자',
    note: '데이터가 하나도 없는 상태',
    role: 'member',
    name: '김지훈',
    title: '영업 담당자',
    owner: '김지훈',
    seeded: false,
  },
  {
    id: 'empty-manager',
    label: '첫 세팅 · 영업 팀장',
    note: '팀은 있고 실적은 아직 없는 상태',
    role: 'manager',
    name: '김서현',
    title: '영업팀장',
    owner: null,
    seeded: false,
  },
]

export const DEFAULT_PROFILE_ID = 'sample-manager'

export function findProfile(id: string | null): MockProfile {
  return (
    MOCK_PROFILES.find((p) => p.id === id) ??
    MOCK_PROFILES.find((p) => p.id === DEFAULT_PROFILE_ID)!
  )
}
