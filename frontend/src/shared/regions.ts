// 지역 도메인. 매핑 시드는 mocks/ 에서 받습니다.
import { regionByOrg } from '@/mocks'

/** 표와 차트의 지역 순서. 실적이 0인 지역도 자리를 지킵니다. */
export const REGIONS = ['서울', '경기', '인천', '충남'] as const

/** 매핑에 없는 회사는 '기타'로 모읍니다. 계약 한 건이 집계에서 사라지지 않게 합니다. */
export function regionOf(org: string): string {
  return regionByOrg[org] ?? '기타'
}
