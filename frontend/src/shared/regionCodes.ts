// 지역 코드 한 벌. member.region_code(팀원 담당지역)와
// customer_company.region_code(고객사 지역)가 같은 코드를 씁니다. 두 곳이 다른 표기를 쓰면
// 나중에 지역별 실적을 셀 때 맞물리지 않습니다.

/** 코드 → 한글 이름. 적는 순서가 곧 선택란에 그려지는 순서입니다. */
export const REGION_LABEL: Record<string, string> = {
  seoul: '서울',
  busan: '부산',
  daegu: '대구',
  incheon: '인천',
  gwangju: '광주',
  daejeon: '대전',
  ulsan: '울산',
  sejong: '세종',
  gyeonggi: '경기',
  gangwon: '강원',
  chungbuk: '충북',
  chungnam: '충남',
  jeonbuk: '전북',
  jeonnam: '전남',
  gyeongbuk: '경북',
  gyeongnam: '경남',
  jeju: '제주',
}

/** 고를 수 있는 코드. */
export const REGION_CODES = Object.keys(REGION_LABEL)

/** 선택란에 그대로 넣는 목록. 맨 앞은 지역을 정하지 않은 상태입니다. */
export const REGION_OPTIONS = [
  { value: '', label: '미지정' },
  ...REGION_CODES.map((code) => ({ value: code, label: REGION_LABEL[code] })),
]

/**
 * 화면에 보일 지역 이름입니다.
 *
 * 모르는 코드는 코드 그대로 보여 줍니다. 목록에 없는 값이 DB 에 남아 있어도 빈칸이 되어
 * 사라지는 것보다 낫습니다. 값이 없을 때 뭐라 적을지는 화면마다 달라 인자로 받습니다.
 */
export function regionLabel(code: string | null, empty = '—'): string {
  if (code === null || code === '') return empty
  return REGION_LABEL[code] ?? code
}
