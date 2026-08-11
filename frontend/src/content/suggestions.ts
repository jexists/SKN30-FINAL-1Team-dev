// 시연용 합성 데이터입니다. 실제 병원·담당자·제품이 아닙니다.
//
// AI 가 제안하는 일정입니다. 근거(basis)는 counters.ts 의 후속 조치·갱신 예정 건과
// customers.ts 의 미접촉 고객에서 뽑은 것처럼 읽히도록 맞춰 두었습니다.
// off 는 agenda.ts 의 일정이 없는 날에 두어, 추천이 빈 칸을 채우는 것으로 보이게 합니다.
import { addDays, iso, TODAY } from '@/utils/date'

import type { AiSuggestion, AiSuggestionSeed } from './types'

const suggestionSeed: AiSuggestionSeed[] = [
  {
    id: 's1',
    off: 3,
    time: '10:00',
    dur: '40분',
    kind: 'call',
    title: '리스 조건표 설명 통화',
    hospital: '새봄정형외과',
    dept: '원무팀',
    contact: '오정민 병원장',
    place: '전화',
    reason:
      '견적 회신이 14일째 없습니다. 자료를 보낸 다음 날 통화로 확인하는 편이 회신율이 높습니다.',
    basis: ['후속 기한 4일 초과', '견적 회신 없음'],
  },
  {
    id: 's2',
    off: 4,
    time: '14:00',
    dur: '60분',
    kind: 'visit',
    title: '유지보수 계약 갱신 사전 협의',
    hospital: '새봄정형외과',
    dept: '원무팀',
    contact: '오정민 병원장',
    place: '원장실',
    reason: 'FM-CT-2025-0112 만료 전에 SonoFlex Pro 도입 건과 묶으면 한 번에 갱신할 수 있습니다.',
    basis: ['계약 만료 D-18', '₩12.4M'],
  },
  {
    id: 's3',
    off: 5,
    time: '11:00',
    dur: '30분',
    kind: 'internal',
    title: 'TCO 비교표 검토 요청',
    hospital: '영업 1팀',
    dept: '내부 회의',
    contact: '김서현 팀장',
    place: '본사 회의실 B',
    reason:
      '한빛대 회신 자료의 경쟁사 납기 항목이 비어 있습니다. 계약 협의 미팅 전에 채워야 합니다.',
    basis: ['후속 기한 초과', '계약 협의 선행'],
  },
  {
    id: 's4',
    off: 7,
    time: '15:00',
    dur: '45분',
    kind: 'edu',
    title: 'OrthoScan Mini 사용 교육 2회차',
    hospital: '서림메디컬센터',
    dept: '영상의학과',
    contact: '윤가영 간호팀장',
    place: '교육실',
    reason: '1회차 참석 인원이 5명이라 교대 근무 인력이 빠집니다. 통상 2회차까지 진행합니다.',
    basis: ['1회차 후속', '교대 인력 미참석'],
  },
  {
    id: 's5',
    off: 10,
    time: '10:30',
    dur: '40분',
    kind: 'visit',
    title: '소모품 공급 단가 조정 면담',
    hospital: '서림메디컬센터',
    dept: '구매팀',
    contact: '한지우 대리',
    place: '본관 4층',
    reason:
      'FM-CT-2025-0129 갱신에 하반기 단가 조정이 선행되어야 합니다. 만료까지 여유가 있을 때 엽니다.',
    basis: ['계약 만료 D-27', '단가 조정 선행'],
  },
  {
    id: 's6',
    off: 13,
    time: '13:30',
    dur: '50분',
    kind: 'demo',
    title: 'CardioView X7 2차 데모',
    hospital: '정우병원',
    dept: '구매팀',
    contact: '최수아 책임',
    place: '회의실',
    reason:
      'OrthoScan 데모 이후 접점이 끊깁니다. 보안 요구사항 회신에 맞춰 다음 접촉을 잡아 두세요.',
    basis: ['다음 일정 없음', '초기 접촉'],
  },
]

/** 실제 날짜가 붙은 추천. 가까운 날짜부터 나옵니다. */
export const aiSuggestions: AiSuggestion[] = suggestionSeed
  .map((seed) => ({ ...seed, date: iso(addDays(TODAY, seed.off)) }))
  .sort((a, b) => a.date.localeCompare(b.date) || a.time.localeCompare(b.time))
