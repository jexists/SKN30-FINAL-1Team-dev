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
  apiStatus?: ApiReportStatus
  version?: number
  currentSubmissionId?: string | null
  /** 팀장이 마지막 검토에서 돌려보낸 이유. 작성자의 note 와 다른 값입니다. */
  reviewNote?: string
}

export type ApiReportKind = 'meeting' | 'daily' | 'weekly' | 'monthly'
export type ApiReportStatus = 'draft' | 'submitted' | 'approved' | 'rejected' | 'changes_requested'

export interface ReportActivityResponse {
  activity_id: string
  title: string
  starts_at: string
}

export interface ReportDealSectionWrite {
  sales_deal_id: string
  deal_snapshot: {
    id: string
    label: string
    note?: string | null
  }
  content: Record<string, unknown>
  position?: number | null
  title?: string | null
  body?: string | null
  structured_values?: Record<string, unknown>
}

export interface ReportDealSectionResponse extends ReportDealSectionWrite {
  position: number | null
  deal_no_snapshot: string | null
  deal_title_snapshot: string | null
  title: string | null
  body: string | null
  structured_values: Record<string, unknown>
  /** 미팅 분석·ML 결과는 서버가 생성하며 조회 응답에만 포함됩니다. */
  ai_evidence: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface ReportResponse {
  id: string
  author_member_id: string
  author_display_name: string
  recipient_member_id: string | null
  recipient_display_name: string | null
  source_activity_id: string | null
  sales_deal_id: string | null
  report_kind: ApiReportKind
  report_date: string
  period_start: string | null
  period_end: string | null
  status_code: ApiReportStatus
  version: number
  generation_input_version: number
  current_submission_id: string | null
  template_snapshot: Record<string, unknown>
  content: Record<string, unknown>
  customer_company_id: string | null
  title: string | null
  body: string | null
  common_body: string | null
  unassigned_body: string | null
  structured_values: Record<string, unknown>
  transcript: string | null
  source_snapshot: Record<string, unknown> | null
  /** AI 가 어느 근거로 채웠는지. 보고서 상세가 그대로 펼쳐 보여 줍니다. */
  ai_evidence: Record<string, unknown> | null
  /** 작성자의 메모. 일일보고서는 여기에 '활동 3건' 같은 제 요약을 넣습니다. */
  note: string | null
  /** 팀장이 반려하며 남긴 사유. 확정하면 비워집니다. 작성자의 note 와 칸이 다릅니다. */
  review_note: string | null
  reviewed_by_member_id: string | null
  reviewed_at: string | null
  activities: ReportActivityResponse[]
  deal_sections: ReportDealSectionResponse[]
  created_at: string
  updated_at: string
}

/** 팀장의 검토 결과. 반려는 changes_requested 로 가서 팀원이 다시 고칠 수 있습니다. */
export interface ReportReviewRequest {
  decision: 'approve' | 'reject'
  reason: string | null
  expected_status_code: 'submitted'
  expected_submission_id: string | null
}

export interface ReportWriteRequest {
  report_kind: ApiReportKind
  report_date: string
  period_start: string | null
  period_end: string | null
  source_activity_id: string | null
  sales_deal_id: string | null
  recipient_member_id: string | null
  template_snapshot: ReportTemplate
  content: Record<string, unknown>
  title?: string | null
  body?: string | null
  common_body?: string | null
  unassigned_body?: string | null
  structured_values?: Record<string, unknown>
  transcript: string | null
  note: string | null
  activity_ids: string[]
  deal_sections: ReportDealSectionWrite[]
}

/** Canonical 보고서를 만들기 전 AgentRun에만 보관하는 생성 입력입니다. */
export interface ReportGenerationRequest {
  idempotency_key: string
  report_kind: ApiReportKind
  report_date: string
  period_start?: string
  period_end?: string
  source_activity_id?: string
  sales_deal_ids?: string[]
  template_snapshot: ReportTemplate
  content: Record<string, unknown>
  transcript?: string
  guidance?: string
}

/** 미확정 AgentRun에 보관되어 재접속 시 작성 화면을 되살리는 원 생성 입력입니다. */
export interface ReportGenerationInput {
  report_kind: ApiReportKind
  report_date: string
  period_start: string | null
  period_end: string | null
  source_activity_id: string | null
  sales_deal_ids: string[]
  template_snapshot: ReportTemplate
  content: Record<string, unknown>
  transcript: string | null
  guidance: string | null
}

/** 같은 논리 보고서 범위의 마지막 미확정 AgentRun을 찾는 조건입니다. */
export interface ReportGenerationScope {
  report_kind: ApiReportKind
  report_date?: string
  period_start?: string
  period_end?: string
  source_activity_id?: string
}

/** 사람이 확인한 최종값을 한 번에 저장하고 제출합니다. */
export interface ReportFinalizeRequest extends ReportWriteRequest {
  idempotency_key: string
  agent_run_id?: string
  report_id?: string
  expected_version?: number
  expected_status_code?: 'draft' | 'changes_requested'
}

export type AgentRunStatus = 'queued' | 'running' | 'completed' | 'partial' | 'failed' | 'cancelled'

export interface ReportDraftSnapshot {
  fields: { field_id: string; value: string }[]
}

export interface DealAssessment {
  features?: Record<string, string>
  label: 'high' | 'watch'
  high_probability: number
  model_version: string
}

export interface MeetingEvidenceLedger {
  schema_version: 'meeting_content.v1'
  transcript_sha256: string
  selected_deal_ids: string[]
  items: {
    segment: { segment_id: string; start: number; end: number; text: string }
    applicability: {
      scope:
        | 'meeting_context'
        | 'company_context'
        | 'all_selected_deals'
        | 'deal'
        | 'unresolved'
        | 'out_of_scope'
      deal_ids: string[]
    }
  }[]
}

export interface MeetingReportBody {
  body: string
  evidence_ids: string[]
}

export interface MeetingSharedNotes {
  common_report: MeetingReportBody | null
  unassigned_report: MeetingReportBody | null
}

export interface MeetingProcessingOutput {
  reports: {
    deal_reports: (MeetingReportBody & { sales_deal_id: string; title: string | null })[]
    common_report: MeetingReportBody | null
    unassigned_report: MeetingReportBody | null
  } | null
  analyses: {
    sales_deal_id: string
    features: Record<string, string> | null
    assessment: DealAssessment | null
    error: string | null
  }[]
  evidence: MeetingEvidenceLedger
  errors: Record<string, string>
  context_lookups?: Record<string, unknown>[]
}

/** 검토·적용 전 화면에서만 보여 주는 문장입니다. ReportWriteRequest에 포함하지 않습니다. */
export interface MeetingPreview {
  section: 'deal' | 'common' | 'unassigned'
  sales_deal_id: string | null
  body: string
  revision: number
}

export interface MeetingProgress {
  run_id: string
  status_code: AgentRunStatus
  stage: string
  previews: MeetingPreview[]
  review_attempt?: number
  review_limit?: number
}

export interface AgentRunResponse<T = ReportDraftSnapshot> {
  id: string
  report_id: string | null
  source_refs: Record<string, unknown>
  generation_input: ReportGenerationInput | null
  status_code: AgentRunStatus
  current_stage_code: string | null
  attempt_count: number
  output_snapshot: T | null
  evidence: Record<string, unknown> | null
  error_code: string | null
  error_message: string | null
  created_at: string | null
}
