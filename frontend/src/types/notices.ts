export interface Notice {
  id?: string
  tag: string
  author: string
  /** 올린 날. 오늘 기준 며칠이며 지난 일이므로 0 이하입니다. */
  postedOff: number
  /** 올린 시각 HH:MM */
  postedAt: string
  /** 목록에 한 줄로 걸리는 제목 */
  text: string
  /** 드로어에서 펼치는 본문 HTML. 서버가 허용 태그만 남겨 보냅니다. */
  detail: string
  /** 본문에 함께 붙는 이미지. 없는 글이 더 많습니다. */
  image?: string
  /** 이미지 대체 텍스트 */
  imageAlt?: string
  /** 지시사항에만 붙는 기한. 공지에는 없습니다. */
  due?: string
  /** 지시를 받은 사람들의 이름. 팀장이 남에게 간 지시를 볼 때 채워집니다. */
  recipients?: string[]
  /** 내가 수신자인 지시일 때만 있습니다. 이행 배지와 이행/미이행 버튼이 이 값을 봅니다. */
  myStatus?: NoticeStatusResponse
}

/** 공지는 팀 전체가, 지시는 지정된 팀원만 봅니다. */
export type NoticeType = 'NOTICE' | 'DIRECTIVE'

export interface NoticeResponse {
  id: string
  scope: 'team' | 'personal'
  type: NoticeType
  author_member_id: string
  author_display_name: string
  /** 수신자가 정확히 한 명일 때만 그 사람입니다. 여러 명이거나 공지면 null 입니다. */
  recipient_member_id: string | null
  tag: string | null
  title: string
  body: string
  image_alt: string | null
  published_at: string
  due_at: string | null
  due_text: string | null
  /** 지시사항이고 내가 수신자일 때만 값이 있습니다. 공지에는 언제나 null 입니다. */
  my_status: NoticeStatusResponse | null
}

/** 지시 이행 여부. pending 은 담당자가 아직 손대지 않은 상태입니다. */
export type NoticeTargetStatus = 'pending' | 'done' | 'not_done'

export interface NoticeStatusResponse {
  status_code: NoticeTargetStatus
  /** 미이행일 때만 채워집니다. */
  status_reason: string | null
  status_changed_at: string | null
}

export interface NoticeTargetResponse extends NoticeStatusResponse {
  id: string
  display_name: string
}

/** 담당자가 자기 몫의 이행 여부를 남깁니다. 미이행이면 사유가 필요합니다. */
export interface NoticeStatusRequest {
  status_code: 'done' | 'not_done'
  reason: string | null
}

/**
 * 팀장 관리 목록의 한 줄. 본문(body)이 없습니다. 본문 속 사진마다 서명 주소를 발급해야 해서
 * 목록에는 싣지 않고, 폼을 열 때 GET /notices/manage/{id} 가 줍니다.
 */
export interface NoticeManageListResponse {
  id: string
  type: NoticeType
  author_member_id: string
  author_display_name: string
  tag: string | null
  title: string
  image_alt: string | null
  published_at: string
  due_at: string | null
  due_text: string | null
  /** YYYY-MM-DD. 시작일과 종료일 모두 그 날을 포함합니다. */
  display_start_date: string
  /** null 이면 무기한입니다. */
  display_end_date: string | null
  is_hidden: boolean
  sort_order: number
  targets: NoticeTargetResponse[]
  target_member_ids: string[]
  updated_at: string
}

/** 수정 폼이 받는 한 건. 목록 항목에 본문을 더한 것입니다. */
export interface NoticeManageResponse extends NoticeManageListResponse {
  body: string
}

export interface NoticeCreateRequest {
  type: NoticeType
  title: string
  body: string
  tag: string | null
  image_alt?: string | null
  due_at?: string | null
  due_text: string | null
  display_start_date: string
  display_end_date: string | null
  is_hidden: boolean
  sort_order: number
  /** 지시에만 보냅니다. 보내면 수신자 전체를 이 목록으로 바꿉니다. */
  target_member_ids: string[] | null
}

export type NoticePatchRequest = Partial<NoticeCreateRequest>

/** 본문에 넣을 사진을 올린 결과. url 은 본문에 그대로 박는 내부 참조입니다. */
export interface NoticeImageResponse {
  id: string
  url: string
}
