// 시연용 합성 데이터입니다. demo/layout_v3.html 에서 옮겼습니다.
// 실제 병원·담당자·제품이 아닙니다.
import { addDays, iso, TODAY } from '@/utils/date'

import type { AgendaItem, AgendaKind, AgendaSeed } from './types'

export const KIND_LABEL: Record<AgendaKind, string> = {
  visit: '방문',
  demo: '데모',
  edu: '교육',
  call: '전화',
  delivery: '납품',
  booth: '학회',
  internal: '내부',
}

const agendaSeed: AgendaSeed[] = [
  {
    id: 'a1',
    off: 0,
    time: '09:30',
    dur: '40분',
    kind: 'visit',
    hospital: '한빛대학교병원',
    dept: '순환기내과',
    contact: '박서준 교수',
    product: 'CardioView X7',
    stage: '계약 협의',
    place: '본관 3층 회의실',
    title: 'CardioView X7 도입 후속 미팅',
    brief:
      '지난 방문에서 제기된 3년 유지보수 비용 이슈에 대응합니다. TCO 비교표와 경쟁사 대비 납기 자료를 지참하고, 4분기 예산 집행 가능 여부와 최종 승인권자를 확인하는 것이 이번 미팅의 목표입니다.',
    history: [
      {
        when: '7일 전',
        what: '제품 테스트 진행. 화면 가독성은 긍정적이었고 유지보수 비용 설명을 요청받았습니다.',
      },
      {
        when: '3주 전',
        what: '순환기내과 과장 면담. 노후 장비 교체 시점을 4분기로 검토 중이라 확인했습니다.',
      },
    ],
    tags: ['우선순위 높음', '견적 검토중'],
    done: true,
  },
  {
    id: 'a2',
    off: 0,
    time: '11:00',
    dur: '30분',
    kind: 'call',
    hospital: '새봄정형외과',
    dept: '원무팀',
    contact: '오정민 병원장',
    product: 'SonoFlex Pro',
    stage: '후속 필요',
    place: '전화',
    title: '견적 회신 지연 건 후속 통화',
    brief:
      '견적 전달 후 14일째 회신이 없습니다. 예산 보류 사유를 확인하고 데모 재일정을 제안합니다. 리스 옵션 안내 자료를 미리 준비하세요.',
    history: [
      { when: '14일 전', what: 'SonoFlex Pro 견적서를 발송했습니다. 회신 없음.' },
      { when: '5주 전', what: '원장 면담에서 초음파 장비 교체 의향을 확인했습니다.' },
    ],
    tags: ['후속 지연'],
    done: false,
  },
  {
    id: 'a3',
    off: 0,
    time: '14:00',
    dur: '60분',
    kind: 'demo',
    hospital: '서림메디컬센터',
    dept: '영상의학과',
    contact: '윤가영 간호팀장',
    product: 'OrthoScan Mini',
    stage: '제품 데모',
    place: '교육실',
    title: '프로브 3종 비교 시연',
    brief:
      '실사용 간호 인력 5명이 참관합니다. 소독 프로토콜과 프로브 교체 주기 질문이 예상됩니다. 데모 장비 반출 확인이 오전 중에 끝나야 합니다.',
    history: [
      { when: '10일 전', what: 'OrthoScan Mini 3대가 입고 완료되어 초기 셋업을 마쳤습니다.' },
      { when: '6주 전', what: '영상의학과 도입 검토 회의에 참석했습니다.' },
    ],
    tags: ['장비 반출'],
    done: false,
  },
  {
    id: 'a4',
    off: 0,
    time: '16:30',
    dur: '30분',
    kind: 'internal',
    hospital: '영업 1팀',
    dept: '내부 회의',
    contact: '김서현 팀장',
    product: '—',
    stage: '주간 점검',
    place: '본사 회의실 B',
    title: '주간 파이프라인 점검',
    brief: '8월 확정 매출 진척과 리스크 딜 2건을 공유합니다. 일일보고서 미작성 3건을 마감합니다.',
    history: [{ when: '지난 주', what: '리스크 딜로 새봄정형외과와 정우병원을 지정했습니다.' }],
    tags: [],
    done: false,
  },
  {
    id: 'a5',
    off: -2,
    time: '10:00',
    dur: '종일',
    kind: 'booth',
    hospital: '대한심장학회 추계학술대회',
    dept: '전시 부스',
    contact: '부스 3-A',
    product: 'CardioView X7',
    stage: '리드 수집',
    place: '코엑스 C홀',
    title: '학술대회 부스 운영 1일차',
    brief: 'CardioView X7 실물 전시와 상담을 진행합니다. 리드 카드는 당일 저녁에 CRM으로 옮깁니다.',
    history: [{ when: '2주 전', what: '부스 위치와 전시 장비 반출 일정을 확정했습니다.' }],
    tags: ['리드 수집'],
    done: true,
  },
  {
    id: 'a6',
    off: -2,
    time: '16:00',
    dur: '50분',
    kind: 'visit',
    hospital: '정우병원',
    dept: '구매팀',
    contact: '최수아 책임',
    product: 'OrthoScan Mini',
    stage: '초기 접촉',
    place: '학회장 미팅룸',
    title: '학회 현장 구매 담당자 면담',
    brief:
      '학회 참석 중인 구매 담당자와 짧게 면담합니다. 기존 시스템 연동 범위와 도입 승인 절차를 확인합니다.',
    history: [{ when: '1개월 전', what: '첫 콜드 콜에서 하반기 검토 의향을 확인했습니다.' }],
    tags: [],
    done: true,
  },
  {
    id: 'a7',
    off: 1,
    time: '09:00',
    dur: '90분',
    kind: 'delivery',
    hospital: '새봄정형외과',
    dept: '원무팀',
    contact: '오정민 병원장',
    product: 'SonoFlex Pro',
    stage: '납품 입회',
    place: '1층 처치실',
    title: 'SonoFlex Pro 납품 입회',
    brief:
      '발주 FM-PO-2026-0021 건의 예상 입고일입니다. 설치 공간은 사전 확인을 마쳤습니다. 입회 후 초기 셋업과 사용 교육 일정을 함께 잡으세요.',
    history: [{ when: '9일 전', what: '본사 생산팀으로 발주를 등록했습니다.' }],
    tags: ['입회 필요'],
    done: false,
  },
  {
    id: 'a8',
    off: 2,
    time: '13:30',
    dur: '60분',
    kind: 'edu',
    hospital: '서림메디컬센터',
    dept: '영상의학과',
    contact: '윤가영 간호팀장',
    product: 'OrthoScan Mini',
    stage: '사용 교육',
    place: '교육실',
    title: 'OrthoScan Mini 사용 교육 1회차',
    brief:
      '데모에서 나온 소독 프로토콜 질문을 교육 자료에 반영해 진행합니다. 참석자 명단은 전날까지 확정합니다.',
    history: [{ when: '2일 후 예정', what: '데모 결과에 따라 교육 범위를 조정합니다.' }],
    tags: [],
    done: false,
  },
  {
    id: 'a9',
    off: 6,
    time: '11:00',
    dur: '45분',
    kind: 'visit',
    hospital: '한빛대학교병원',
    dept: '구매팀',
    contact: '이도현 과장',
    product: 'CardioView X7',
    stage: '계약 협의',
    place: '본관 2층',
    title: 'CardioView X7 계약 조건 협의',
    brief: '발주 FM-PO-2026-0020의 분할 납품 2차 일정과 계약 조건을 함께 정리합니다.',
    history: [{ when: '13일 전', what: '1차 분할 납품분을 발주했습니다.' }],
    tags: [],
    done: false,
  },
  {
    id: 'a10',
    off: -6,
    time: '14:00',
    dur: '40분',
    kind: 'visit',
    hospital: '한빛대학교병원',
    dept: '순환기내과',
    contact: '박서준 교수',
    product: 'CardioView X7',
    stage: '제품 테스트',
    place: '본관 3층',
    title: 'CardioView X7 제품 테스트',
    brief:
      '실사용 테스트를 진행했습니다. 화면 가독성은 긍정적이었고 유지보수 비용 설명 요청을 받았습니다.',
    history: [{ when: '당일', what: '테스트 결과를 정리해 브리핑에 반영했습니다.' }],
    tags: [],
    done: true,
  },
  {
    id: 'a11',
    off: 8,
    time: '10:30',
    dur: '40분',
    kind: 'visit',
    hospital: '정우병원',
    dept: '구매팀',
    contact: '최수아 책임',
    product: 'OrthoScan Mini',
    stage: '제품 데모',
    place: '회의실',
    title: 'OrthoScan Mini 본원 데모',
    brief:
      '학회 면담 후속으로 본원에서 데모를 진행합니다. 보안 요구사항과 데이터 접근 권한을 확인하세요.',
    history: [{ when: '학회 당일', what: '구매 담당자와 첫 면담을 진행했습니다.' }],
    tags: [],
    done: false,
  },
]

/** 날짜 키 → 그날의 일정(시간순). offset 을 실제 날짜로 편 결과입니다. */
export const agendaByDate: Record<string, AgendaItem[]> = {}

for (const seed of agendaSeed) {
  const date = iso(addDays(TODAY, seed.off))
  ;(agendaByDate[date] ??= []).push({ ...seed, date })
}

for (const list of Object.values(agendaByDate)) {
  list.sort((a, b) => a.time.localeCompare(b.time))
}

export function agendaFor(dateISO: string): AgendaItem[] {
  return agendaByDate[dateISO] ?? []
}
