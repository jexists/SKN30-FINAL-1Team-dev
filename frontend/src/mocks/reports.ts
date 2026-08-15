// 업무보고 양식과 이력. 시연용 합성 데이터입니다.
import { addDays, iso, TODAY } from '@/utils/date'

import type { DailyReportSeed, ReportActivity, ReportTemplate } from '@/types'

export const dailyTemplate: ReportTemplate = {
  id: 'tpl-sales-1',
  name: '영업 1팀 일일보고 양식',
  owner: '김서현 영업팀장',
  updated: iso(addDays(TODAY, -11)),
  fields: [
    {
      id: 'summary',
      label: '업무 요약',
      type: 'textarea',
      required: true,
      aiFilled: true,
      placeholder: '오늘 진행한 활동을 요약합니다.',
    },
    {
      id: 'issue',
      label: '특이사항 · 이슈',
      type: 'textarea',
      required: false,
      aiFilled: true,
      placeholder: '지연, 고객 불만, 예산 보류 등',
      hint: '팀 주간 회의에서 이 항목만 모아 봅니다.',
    },
    {
      id: 'next',
      label: '내일 계획',
      type: 'textarea',
      required: true,
      aiFilled: true,
      placeholder: '내일 처리할 후속 업무',
    },
    {
      id: 'competitor',
      label: '경쟁사 동향',
      type: 'text',
      required: false,
      aiFilled: false,
      placeholder: '들은 내용이 있으면 한 줄로',
      hint: '팀장이 추가한 항목입니다. 직접 확인한 것만 적으세요.',
    },
  ],
}

/**
 * 주간·월간 양식. 지금은 이력에 남은 보고서를 읽을 때 필드 라벨을 얻는 용도뿐입니다.
 * 주간·월간 작성 화면은 아직 없습니다.
 */
export const weeklyTemplate: ReportTemplate = {
  id: 'tpl-sales-w',
  name: '영업 1팀 주간보고 양식',
  owner: '김서현 영업팀장',
  updated: iso(addDays(TODAY, -11)),
  fields: [
    { id: 'result', label: '주간 성과', type: 'textarea', required: true, aiFilled: false },
    { id: 'plan', label: '다음 주 계획', type: 'textarea', required: true, aiFilled: false },
    { id: 'risk', label: '리스크', type: 'textarea', required: false, aiFilled: false },
  ],
}

export const monthlyTemplate: ReportTemplate = {
  id: 'tpl-sales-m',
  name: '영업 1팀 월간보고 양식',
  owner: '영업본부장',
  updated: iso(addDays(TODAY, -40)),
  fields: [
    { id: 'perf', label: '월간 실적', type: 'textarea', required: true, aiFilled: false },
    { id: 'gap', label: '목표 대비', type: 'textarea', required: true, aiFilled: false },
    { id: 'focus', label: '다음 달 중점', type: 'textarea', required: false, aiFilled: false },
  ],
}

/** 보고서 종류에 맞는 양식. 상세와 drawer 가 필드 라벨을 여기서 얻습니다. */

export const APPROVERS = ['김서현 영업팀장', '영업본부장'] as const

/** 캘린더 밖에서 붙는 활동. 날짜 offset 별로 몇 건씩 섞어 둡니다. */

export const extraActivitySeed: Record<number, Omit<ReportActivity, 'included'>[]> = {
  0: [
    {
      id: 'x-today-1',
      source: '미팅보고서',
      title: '한빛대학교병원 미팅 기록 확정',
      desc: '필수 확인 5개 중 4개 완료 · 유지보수 조건 추가 설명 요청',
    },
    {
      id: 'x-today-2',
      source: '문서',
      title: 'CardioView X7 견적서 발송',
      desc: 'FM-QT-2026-0812 · 총액 50,160,000원',
    },
    {
      id: 'x-today-3',
      source: '후속',
      title: '새봄정형외과 후속 방문 미등록',
      desc: '견적 회신 예정일 2일 경과',
    },
  ],
  [-1]: [
    {
      id: 'x-d1-1',
      source: '미팅보고서',
      title: '정우병원 구매팀 통화 기록',
      desc: '도입 승인 절차 확인 · 하반기 검토 유지',
    },
  ],
  [-2]: [
    {
      id: 'x-d2-1',
      source: '문서',
      title: '학술대회 리드 카드 12건 CRM 등록',
      desc: '부스 3-A · 후속 대상 4곳 분류 완료',
    },
  ],
}

/**
 * 그날 보고서에 넣을 후보 활동. 캘린더 일정이 기본이고 나머지가 뒤에 붙습니다.
 *
 * 날짜를 인자로 받으므로 밀린 날짜를 소급 작성할 때도 그대로 씁니다.
 */

export const reportSeed: DailyReportSeed[] = [
  {
    id: 'dr-1',
    owner: '김지훈',
    off: -1,
    kind: '일일',
    approver: '김서현 영업팀장',
    status: '확정',
    note: '방문 2건 · 통화 1건',
    values: {
      summary:
        '· 정우병원 구매팀 최수아 책임과 도입 승인 절차를 확인했습니다.\n· 한빛대학교병원 분할 납품 2차 일정을 조율했습니다.',
      issue: '정우병원은 하반기 예산 확정 전까지 결정을 미루고 있습니다.',
      next: '새봄정형외과 견적 회신 독촉, 서림메디컬센터 데모 자료 최종 점검',
      competitor: '',
    },
    activities: [],
    attachments: [],
  },
  {
    id: 'dr-2',
    owner: '김지훈',
    off: -2,
    kind: '일일',
    approver: '김서현 영업팀장',
    status: '반려',
    note: '학회 부스 1일차',
    values: {
      summary: '· 대한심장학회 부스를 운영하고 리드 카드 12건을 수집했습니다.',
      issue: '',
      next: '수집한 리드 중 후속 대상 4곳을 분류합니다.',
      competitor: '경쟁사도 같은 홀에 부스를 냈습니다.',
    },
    activities: [],
    attachments: [],
  },
  {
    id: 'dr-3',
    owner: '김지훈',
    off: -6,
    kind: '일일',
    approver: '김서현 영업팀장',
    status: '확정',
    note: '제품 테스트 1건',
    values: {
      summary: '· 한빛대학교병원에서 CardioView X7 실사용 테스트를 진행했습니다.',
      issue: '유지보수 비용 설명 자료를 추가로 요청받았습니다.',
      next: 'TCO 비교표를 만들어 다음 방문 때 지참합니다.',
      competitor: '',
    },
    activities: [],
    attachments: [],
  },
  {
    id: 'dr-4',
    owner: '김지훈',
    off: -7,
    kind: '일일',
    approver: '김서현 영업팀장',
    status: '확정',
    note: '내부 회의 1건',
    values: {
      summary: '· 주간 파이프라인 점검 회의에 참석했습니다.',
      issue: '',
      next: '리스크 딜 2건의 후속 일정을 잡습니다.',
      competitor: '',
    },
    activities: [],
    attachments: [],
  },
  {
    id: 'dr-5',
    owner: '김지훈',
    off: -8,
    kind: '일일',
    approver: '영업본부장',
    status: '확정',
    note: '방문 1건 · 견적 1건',
    values: {
      summary: '· 새봄정형외과에 SonoFlex Pro 견적서를 발송했습니다.',
      issue: '',
      next: '회신을 기다리며 리스 옵션 자료를 준비합니다.',
      competitor: '',
    },
    activities: [],
    attachments: [],
  },
  {
    id: 'dr-6',
    owner: '김지훈',
    off: -9,
    kind: '일일',
    approver: '김서현 영업팀장',
    status: '확정',
    note: '전화 3건',
    values: {
      summary: '· 기존 거래처 3곳에 정기 점검 일정을 안내했습니다.',
      issue: '',
      next: '점검 일정을 캘린더에 등록합니다.',
      competitor: '',
    },
    activities: [],
    attachments: [],
  },

  // 주간·월간은 이력에서 읽기만 합니다. 작성 화면은 아직 없습니다.
  // 제출일은 기간이 끝난 다음 근무일이라 일일보고와 같은 날에 겹칩니다.
  {
    id: 'wr-1',
    owner: '김지훈',
    off: -2,
    kind: '주간',
    period: '8/3 – 8/9',
    approver: '영업본부장',
    status: '확정',
    note: '방문 7건 · 견적 3건',
    values: {
      result:
        '· 신규 리드 12건을 확보하고 견적 3건을 발송했습니다.\n· 학술대회 부스로 인지도를 넓혔습니다.',
      plan: '견적 3건의 회신을 받고 후속 방문 4건을 잡습니다.',
      risk: '정우병원 예산 확정이 하반기로 밀릴 수 있습니다.',
    },
    activities: [],
    attachments: [],
  },
  {
    id: 'wr-2',
    owner: '김지훈',
    off: -9,
    kind: '주간',
    period: '7/27 – 8/2',
    approver: '영업본부장',
    status: '확정',
    note: '방문 5건 · 견적 1건',
    values: {
      result: '· 기존 거래처 정기 점검 일정을 모두 확정했습니다.',
      plan: '학술대회 부스 운영 준비를 마칩니다.',
      risk: '',
    },
    activities: [],
    attachments: [],
  },
  {
    id: 'mr-1',
    owner: '김지훈',
    off: -7,
    kind: '월간',
    period: '2026년 7월',
    approver: '영업본부장',
    status: '확정',
    note: '수주 4건 · 신규 리드 31건',
    values: {
      perf: '· 수주 4건, 총 2억 1,400만원.\n· 신규 리드 31건 중 8건이 견적 단계로 넘어갔습니다.',
      gap: '목표 대비 94%. 미달분은 정우병원 건의 이월 때문입니다.',
      focus: 'CardioView X7 도입 병원 3곳을 8월 안에 확정합니다.',
    },
    activities: [],
    attachments: [],
  },
]

/** offset 을 실제 날짜로 편 제출 이력. 최근 것이 앞에 옵니다. */
