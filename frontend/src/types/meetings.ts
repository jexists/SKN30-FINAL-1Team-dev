import type { ReportAttachment, ReportStatus, ReportTemplate } from './reports'

/**
 * 미팅 한 건의 기록. 캘린더 일정(AgendaItem) 하나에 붙습니다.
 *
 * 병원·담당자 같은 값은 일정에서 그대로 복사해 둡니다. 나중에 일정이 바뀌어도
 * 그때 만난 상대가 남아 있어야 기록으로서 뜻이 있습니다.
 */
export interface MeetingReportSeed {
  id: string
  /** 작성자 */
  owner: string
  /** 어느 일정에서 왔는지. AgendaItem.id */
  agendaId: string
  /** 오늘로부터 며칠. 과거이므로 0 이하입니다. */
  off: number
  time: string
  hospital: string
  dept: string
  contact: string
  product: string
  place: string
  /** 일정 제목이 그대로 미팅 제목이 됩니다. */
  title: string
  status: ReportStatus
  /** 직접 입력한 미팅 내용. 나중에 STT 결과가 들어올 자리입니다. */
  transcript: string
  /** ReportFieldDef.id → 입력값 */
  values: Record<string, string>
  attachments: ReportAttachment[]
  /** AI 가 어디를 보고 채웠는지 한 줄 */
  evidence?: string
}

/** 실제 날짜가 붙은 미팅보고서. date 는 미팅한 날입니다. */
export interface MeetingReport extends MeetingReportSeed {
  /** YYYY-MM-DD */
  date: string
  template: ReportTemplate
}
