/** 팀장이 정한 보고 양식의 항목 하나. 화면은 이 배열을 그대로 그립니다. */
export interface ReportFieldDef {
  id: string
  label: string
  type: 'text' | 'textarea' | 'select'
  required: boolean
  placeholder?: string
  /** select 전용 */
  options?: string[]
  /** AI 초안이 채울 수 있는 항목인지. false 면 사람이 직접 씁니다. */
  aiFilled: boolean
  /** 팀장이 붙인 안내문 */
  hint?: string
}

/**
 * 팀장이 관리하는 보고 양식. 이번 범위에서는 읽기만 합니다.
 * 필드를 코드에 박지 않고 여기서 받아 와야 팀마다 다른 양식을 받을 수 있습니다.
 */
export interface ReportTemplate {
  id: string
  name: string
  owner: string
  updated: string
  fields: ReportFieldDef[]
}

/** 활동을 어디서 주워 왔는지. 배지로 나옵니다. */
export type ActivitySource = '캘린더' | '미팅보고서' | '문서' | '후속' | '수기'

/** 보고서에 넣을 후보 활동 한 건 */
export interface ReportActivity {
  id: string
  source: ActivitySource
  title: string
  desc: string
  /** 체크를 풀면 보고서와 AI 입력에서 함께 빠집니다. */
  included: boolean
}

export type AttachmentKind = 'audio' | 'image' | 'pdf'
export type AttachmentState = 'analyzing' | 'done' | 'failed'

/** 음성·사진·PDF 첨부. 어디까지나 선택 사항입니다. */
export interface ReportAttachment {
  id: string
  kind: AttachmentKind
  name: string
  /** '2.4MB' 처럼 표시용입니다. */
  size: string
  state: AttachmentState
  /** 분석이 끝나면 채워집니다. 초안 생성의 입력이자 근거입니다. */
  extract?: string
}

export type ReportStatus = '작성중' | '검토 대기' | '확정' | '반려'

/** 보고서 종류. 작성 흐름은 아직 일일만 있고 주간·월간은 이력에서 읽기만 합니다. */
export type ReportKind = '일일' | '주간' | '월간'

export interface DailyReportSeed {
  id: string
  /** 작성자 */
  owner: string
  /** 오늘로부터 며칠. 과거이므로 음수입니다. */
  off: number
  kind: ReportKind
  approver: string
  status: ReportStatus
  /** ReportFieldDef.id → 입력값 */
  values: Record<string, string>
  activities: ReportActivity[]
  attachments: ReportAttachment[]
  /** 이력 목록에 한 줄로 붙는 설명 */
  note: string
  /** 주간·월간이 덮는 기간. 목록 제목에 붙습니다. 일일은 date 로 충분해 비어 있습니다. */
  period?: string
}

/** 실제 날짜가 붙은 업무보고. date 는 제출일입니다. */
export interface DailyReport extends DailyReportSeed {
  /** YYYY-MM-DD */
  date: string
}
