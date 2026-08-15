// 대시보드 KPI 목록. 시연용 합성 데이터입니다.
// KPI 타일의 숫자는 이 목록들에서 파생됩니다 — 타일과 목록이 어긋날 수 없게 하려는 것입니다.
import type { CsRequest, FollowUp, Renewal } from '@/types'

export const followUps: FollowUp[] = [
  {
    task: '리스 옵션 안내 자료 발송',
    org: '새봄정형외과',
    owner: '이수민',
    who: '원무팀 · 오정민 병원장',
    note: '견적 회신이 14일째 없습니다. 리스 조건표를 먼저 보내고 통화로 확인하세요.',
    dueOff: -4,
  },
  {
    task: '3년 유지보수 TCO 비교표 회신',
    org: '한빛대학교병원',
    owner: '김지훈',
    who: '순환기내과 · 박서준 교수',
    note: '테스트 후 요청받은 자료입니다. 경쟁사 대비 납기 항목까지 채워야 합니다.',
    dueOff: -1,
  },
  {
    task: '분할 납품 2차 일정 확정',
    org: '한빛대학교병원',
    owner: '김지훈',
    who: '구매팀 · 이도현 과장',
    note: 'FM-PO-2026-0020의 잔여 1대 일정입니다. 생산팀 회신을 받은 뒤 통보하세요.',
    dueOff: 1,
  },
  {
    task: '교육 참석자 명단 취합',
    org: '서림메디컬센터',
    owner: '김지훈',
    who: '영상의학과 · 윤가영 간호팀장',
    note: '사용 교육 1회차 전날까지 확정해야 교재 부수를 맞출 수 있습니다.',
    dueOff: 1,
  },
  {
    task: '보안 요구사항 문서 요청',
    org: '정우병원',
    owner: '박도윤',
    who: '구매팀 · 최수아 책임',
    note: '본원 데모 전에 데이터 접근 권한 범위를 문서로 받아야 합니다.',
    dueOff: 3,
  },
  {
    task: 'SonoFlex Pro 설치 일정 회신',
    org: '새봄정형외과',
    owner: '이수민',
    who: '원무팀 · 오정민 병원장',
    note: '입회 후 초기 셋업과 사용 교육 일정을 묶어서 제안하세요.',
    dueOff: 4,
  },
  {
    task: '소모품 단가표 갱신본 전달',
    org: '서림메디컬센터',
    owner: '김지훈',
    who: '구매팀 · 한지우 대리',
    note: '하반기 단가 조정분을 반영한 표를 전달합니다.',
    dueOff: 9,
  },
]

export const csRequests: CsRequest[] = [
  {
    issue: '부팅 시 화면 깜빡임',
    org: '한빛대학교병원',
    owner: '김지훈',
    who: '순환기내과 · 박서준 교수',
    product: 'CardioView X7',
    state: '미응답',
    urgent: true,
    agoOff: 0,
    ago: '6시간 전 접수',
    note: '진료 중 재현되어 사용을 중단한 상태입니다. 기술지원팀 배정이 필요합니다.',
  },
  {
    issue: '프로브 케이블 접촉 불량',
    org: '서림메디컬센터',
    owner: '김지훈',
    who: '영상의학과 · 윤가영 간호팀장',
    product: 'OrthoScan Mini',
    state: '미응답',
    urgent: false,
    agoOff: -1,
    ago: '1일 전 접수',
    note: '프로브 3종 중 1종에서만 발생합니다. 교체용 케이블 재고를 확인하세요.',
  },
  {
    issue: '젤 워머 온도 편차',
    org: '새봄정형외과',
    owner: '이수민',
    who: '원무팀 · 오정민 병원장',
    product: 'SonoFlex Pro',
    state: '처리중',
    urgent: false,
    agoOff: -2,
    ago: '2일 전 접수',
    note: '기술지원팀이 원격 점검 중입니다. 결과 회신 예정입니다.',
  },
  {
    issue: '패드 접착력 저하 문의',
    org: '한빛대학교병원',
    owner: '김지훈',
    who: '구매팀 · 이도현 과장',
    product: '전극 패드 (소모품)',
    state: '처리중',
    urgent: false,
    agoOff: -3,
    ago: '3일 전 접수',
    note: '보관 온도 가이드를 안내했고 교체분 발송 여부를 검토 중입니다.',
  },
]

export const renewals: Renewal[] = [
  {
    org: '새봄정형외과',
    owner: '이수민',
    who: '원무팀 · 오정민 병원장',
    contract: 'FM-CT-2025-0112',
    kind: '유지보수 계약',
    amount: 12_400_000,
    expireOff: 18,
    note: 'SonoFlex Pro 도입 건과 함께 조건을 재협의하면 묶어서 갱신할 수 있습니다.',
  },
  {
    org: '서림메디컬센터',
    owner: '김지훈',
    who: '구매팀 · 한지우 대리',
    contract: 'FM-CT-2025-0129',
    kind: '소모품 공급 계약',
    amount: 7_800_000,
    expireOff: 27,
    note: '하반기 단가 조정분 반영이 선행되어야 합니다.',
  },
]

/** 월 매출 목표. 진행률은 achieved/target 에서 파생합니다. */
export const salesGoal = {
  month: 8,
  achieved: 189_900_000,
  target: 300_000_000,
  /** 마감까지 남은 일수 */
  deadlineInDays: 21,
  teamName: '영업 1팀',
}
