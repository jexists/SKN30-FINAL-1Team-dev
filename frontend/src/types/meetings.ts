import type {
  ApiReportStatus,
  DealAssessment,
  MeetingEvidenceLedger,
  MeetingSharedNotes,
  ReportAttachment,
  ReportStatus,
  ReportTemplate,
} from './reports'

/**
 * 업무보고서를 팀장이 어디까지 봤는지.
 *
 * 서버 status_code 네 가지에 보류 하나를 더한 것입니다. 이름표와 색은
 * pages/Meetings/reviewStatus.ts 가 붙입니다.
 */
export type MeetingReview = 'writing' | 'submitted' | 'approved' | 'needsMore' | 'hold'

/** 미팅에 연결한 영업 현황 한 건. 고를 때 본 이름표를 그대로 남깁니다. */
export interface MeetingDealRef {
  id: string
  /** 딜 번호처럼 사람이 부르는 이름 */
  label: string
  /** 제목·단계처럼 딜을 가리는 데 필요한 곁말 */
  note?: string
}

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
  /** 보고 흐름상의 상태. 일일보고가 이 값으로 활동을 끌어올릴지 가립니다. */
  status: ReportStatus
  /** 팀장 확인 단계. 상세 화면 배지와 수정 잠금이 이 값만 봅니다. */
  review: MeetingReview
  /** 저장·Agent 실행 가능 여부를 서버 코드 그대로 판단할 때 씁니다. */
  apiStatus?: ApiReportStatus
  /** 직접 입력한 미팅 내용. 나중에 STT 결과가 들어올 자리입니다. */
  transcript: string
  /** ReportFieldDef.id → 입력값 */
  values: Record<string, string>
  attachments: ReportAttachment[]
  /** 이 보고서가 다루는 딜. 기존 합성 데이터는 값이 없을 수 있습니다. */
  salesDealId?: string | null
  /** 딜이 바뀌어도 보고서 작성 당시 이름을 보여 주기 위한 스냅샷입니다. */
  salesDeal?: MeetingDealRef
  /** AI 가 어디를 보고 채웠는지 한 줄 */
  evidence?: string
  /**
   * AI 가 최초로 만든 원본. values 와 따로 둡니다.
   *
   * 사용자가 values 를 아무리 고쳐도 이 값은 바뀌지 않아야 "AI 는 뭐라고 썼더라" 를
   * 되짚을 수 있습니다. 한 벌로 관리하면 첫 수정에서 원본이 사라집니다.
   */
  aiValues?: Record<string, string>
  aiEvidence?: string
  /** 원본을 만든 시각. ISO 8601 */
  aiGeneratedAt?: string
  meetingRunId?: string
  meetingShared?: MeetingSharedNotes
  evidenceLedger?: MeetingEvidenceLedger
  assessment?: DealAssessment
  analysisError?: string
  reportError?: string
}

/** 실제 날짜가 붙은 업무보고서. date 는 미팅한 날입니다. */
export interface MeetingReport extends MeetingReportSeed {
  /** YYYY-MM-DD */
  date: string
  /** 작성자의 구성원 번호. 고칠 수 있는 사람인지 이 값으로 가립니다. */
  ownerMemberId: string
  template: ReportTemplate
  updatedAt?: string
}
