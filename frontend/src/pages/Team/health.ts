// 달성률로 사람을 가르는 눈금입니다.
//
// 목록의 상태 배지와 '확인이 필요한 구성원' 카드가 같은 기준을 봐야 합니다. 한쪽만
// 눈금을 옮기면 목록에서는 '주의'인 사람이 위쪽 카드에는 안 뜨는 일이 생깁니다.
import type { StatusTone } from '@/components/StatusBadge'

/** 이만큼 왔으면 팀장이 따로 볼 일이 없습니다. */
export const HEALTHY = 70
/** 이 아래는 이달 안에 따라잡기 어렵습니다. */
export const WATCH = 40

export function health(rate: number | null): { label: string; tone: StatusTone } {
  // 목표를 세우지 않았으면 잘하고 못하고를 말할 수 없습니다.
  if (rate === null) return { label: '미설정', tone: 'neutral' }
  if (rate >= HEALTHY) return { label: '정상', tone: 'green' }
  if (rate >= WATCH) return { label: '주의', tone: 'orange' }
  return { label: '위험', tone: 'red' }
}
