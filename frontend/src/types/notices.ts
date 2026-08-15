export interface Notice {
  tag: string
  author: string
  /** 올린 날. 오늘 기준 며칠이며 지난 일이므로 0 이하입니다. */
  postedOff: number
  /** 올린 시각 HH:MM */
  postedAt: string
  /** 목록에 한 줄로 걸리는 제목 */
  text: string
  /** 드로어에서 펼치는 본문 */
  detail: string
  /** 본문에 함께 붙는 이미지. 없는 글이 더 많습니다. */
  image?: string
  /** 이미지 대체 텍스트 */
  imageAlt?: string
  /** 지시사항에만 붙는 기한. 공지에는 없습니다. */
  due?: string
}
