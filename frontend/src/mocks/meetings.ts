// 미팅보고서 목록이 API 로 채워지지 않을 때 쓰는 시연용 합성 데이터입니다.
import { meetingTemplate } from '@/shared/meetings'
import type { MeetingReport, MeetingReportSeed } from '@/types'
import { addDays, iso, TODAY } from '@/utils/date'

export const meetingReportSeed: MeetingReportSeed[] = [
  {
    id: 'mt-a10',
    agendaId: 'a10',
    off: -6,
    time: '14:00',
    hospital: '한빛대학교병원',
    owner: '김지훈',
    dept: '순환기내과',
    contact: '박서준 교수',
    product: 'CardioView X7',
    place: '본관 3층',
    title: 'CardioView X7 제품 테스트',
    status: '확정',
    review: 'approved',
    transcript:
      '박서준 교수님과 CardioView X7 테스트 결과를 확인했다. 화면 가독성은 좋았지만 유지보수 비용이 기존 장비보다 높다는 의견이 있었다. 구매팀 이민호 과장에게 다음 주 화요일까지 비교 견적과 유지보수 범위표를 보내기로 했다.',
    values: {
      attendees: '박서준 교수 · 이민호 구매팀 과장',
      reaction: '화면 가독성은 긍정적 · 유지보수 비용이 기존 장비보다 높다는 우려',
      decision: '비교 견적과 유지보수 범위표를 전달하기로 했습니다.',
      next: '다음 주 화요일까지 자료 전달 · 이후 후속 미팅 일정 조율',
      note: '',
    },
    attachments: [],
    evidence: '원문 근거: “이민호 과장에게”, “다음 주 화요일까지”, “유지보수 비용이 높다”.',
  },
  {
    id: 'mt-a6',
    agendaId: 'a6',
    off: -2,
    time: '16:00',
    hospital: '정우병원',
    owner: '박도윤',
    dept: '구매팀',
    contact: '최수아 책임',
    product: 'OrthoScan Mini',
    place: '학회장 미팅룸',
    title: '학회 현장 구매 담당자 면담',
    status: '확정',
    review: 'submitted',
    transcript:
      '최수아 책임과 학회장에서 짧게 면담했다. 기존 시스템 연동 범위를 확인했고 도입 승인은 하반기 예산 확정 이후에 진행된다고 했다.',
    values: {
      attendees: '최수아 구매팀 책임',
      reaction: '기존 시스템 연동 범위에 관심 · 도입 시점은 유보',
      decision: '본원 데모를 진행하기로 했습니다.',
      next: '보안 요구사항과 데이터 접근 권한을 확인한 뒤 본원 데모 일정 확정',
      note: '하반기 예산 확정 전까지 승인 절차는 시작되지 않습니다.',
    },
    attachments: [],
    evidence: '원문 근거: “하반기 예산 확정 이후”, “기존 시스템 연동 범위”.',
  },
]

/** offset 을 실제 날짜로 편 미팅 기록. 최근 것이 앞에 옵니다. */
export const fallbackMeetingReports: MeetingReport[] = meetingReportSeed
  .map((seed) => ({ ...seed, date: iso(addDays(TODAY, seed.off)), template: meetingTemplate }))
  .sort((a, b) => b.date.localeCompare(a.date))
