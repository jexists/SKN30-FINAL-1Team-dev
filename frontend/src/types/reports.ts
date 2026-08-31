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

/**
 * 활동을 어디서 주워 왔는지. 배지로 나옵니다.
 *
 * 보고는 일정/업무보고서 → 일일 → 주간 → 월간 순으로 쌓입니다. 주간·월간은
 * 한 단계 아래 보고서를 자료로 삼으므로 그 둘도 출처가 됩니다.
 */
export type ActivitySource =
  '캘린더' | '업무보고서' | '문서' | '후속' | '수기' | '일일보고서' | '주간보고서'

/** 보고서에 넣을 후보 활동 한 건 */
export interface ReportActivity {
  id: string
  source: ActivitySource
  title: string
  desc: string
  /** 체크를 풀면 보고서와 AI 입력에서 함께 빠집니다. */
  included: boolean
  /**
   * 이 활동이 나온 원본의 id. 업무보고서·일일보고서·주간보고서면 그 보고서 id,
   * 캘린더면 일정 id 입니다. 제출한 뒤에도 무엇을 근거로 썼는지 되짚을 수 있게 남깁니다.
   */
  refId?: string
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

/** 보고서 종류. 주간은 일일보고서를, 월간은 주간보고서를 자료로 씁니다. */
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
  /** 자료에 없는 것을 직접 적은 내용. AI 가 자료와 함께 읽습니다. */
  transcript?: string
  /** 이력 목록에 한 줄로 붙는 설명 */
  note: string
  /** 주간·월간이 덮는 기간. 목록 제목에 붙습니다. 일일은 date 로 충분해 비어 있습니다. */
  period?: string
}

/** 실제 날짜가 붙은 업무보고. date 는 제출일입니다. */
export interface DailyReport extends DailyReportSeed {
  /** YYYY-MM-DD */
  date: string
  /** 작성자의 구성원 번호. 고칠 수 있는 사람인지 이 값으로 가립니다. */
  ownerMemberId: string
  template: ReportTemplate
}

export type ApiReportKind = 'meeting' | 'daily' | 'weekly' | 'monthly'
export type ApiReportStatus = 'draft' | 'submitted' | 'approved' | 'rejected'

export interface ReportActivityResponse {
  activity_id: string
  title: string
  starts_at: string
}

export interface ReportResponse {
  id: string
  author_member_id: string
  author_display_name: string
  recipient_member_id: string | null
  recipient_display_name: string | null
  source_activity_id: string | null
  report_kind: ApiReportKind
  report_date: string
  period_start: string | null
  period_end: string | null
  status_code: ApiReportStatus
  template_snapshot: Record<string, unknown>
  content: Record<string, unknown>
  transcript: string | null
  note: string | null
  activities: ReportActivityResponse[]
  created_at: string
  updated_at: string
}

export interface ReportWriteRequest {
  report_kind: ApiReportKind
  report_date: string
  period_start: string | null
  period_end: string | null
  source_activity_id: string | null
  recipient_member_id: string | null
  template_snapshot: ReportTemplate
  content: Record<string, unknown>
  transcript: string | null
  note: string | null
  activity_ids: string[]
}

export type AgentRunStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface AgentRunResponse {
  id: string
  status_code: AgentRunStatus
  output_snapshot: {
    fields?: { field_id: string; value: string }[]
    summary?: string
  } | null
  evidence: { summary?: string } | null
  error_message: string | null
}
