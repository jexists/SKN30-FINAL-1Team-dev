export interface AppNotification {
  id: string
  /** 목록에 한 줄로 걸리는 내용 */
  text: string
  /** 받은 날. 오늘 기준 며칠이며 지난 일이므로 0 이하입니다. */
  postedOff: number
  /** 받은 시각 HH:MM */
  postedAt: string
  read: boolean
  /** 클릭하면 갈 곳. constants/routes.ts 의 값·빌더를 씁니다. */
  to: string
}
