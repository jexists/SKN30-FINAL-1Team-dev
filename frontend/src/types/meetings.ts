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
export type MeetingReportStatus = Exclude<ReportStatus, '작성중'> | '수정중'

/** 미팅에 연결한 영업 현황 한 건. 고를 때 본 이름표를 그대로 남깁니다. */
export interface MeetingDealRef {
  id: string
  /** 딜 번호처럼 사람이 부르는 이름 */
  label: string
  /** 제목·단계처럼 딜을 가리는 데 필요한 곁말 */
  note?: string
}

/** 미팅 보고서 안에서 딜 하나가 차지하는 본문과 분석 결과입니다. */
export interface MeetingDealSection {
  salesDealId: string
  salesDeal: MeetingDealRef
  product: string
  title: string
  values: Record<string, string>
  evidence?: string
  aiValues: Record<string, string>
  aiEvidence?: string
  aiGeneratedAt?: string
  /** 서버가 저장한 미팅 분석 원본. 사람이 본문을 저장해도 그대로 돌려보냅니다. */
  analysisEvidence: Record<string, unknown> | null
  assessment?: DealAssessment
  analysisError?: string
  reportError?: string
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
  place: string
  /** 일정 제목이 그대로 미팅 제목이 됩니다. */
  title: string
  /** 보고 흐름상의 상태. 일일보고가 이 값으로 활동을 끌어올릴지 가립니다. */
  status: MeetingReportStatus
  /** 팀장 확인 단계. 상세 화면 배지와 수정 잠금이 이 값만 봅니다. */
  review: MeetingReview
  /** 저장·Agent 실행 가능 여부를 서버 코드 그대로 판단할 때 씁니다. */
  apiStatus?: ApiReportStatus
  /** 직접 입력한 미팅 내용. 나중에 STT 결과가 들어올 자리입니다. */
  transcript: string
  attachments: ReportAttachment[]
  dealSections: MeetingDealSection[]
  meetingRunId?: string
  meetingShared?: MeetingSharedNotes
  evidenceLedger?: MeetingEvidenceLedger
}

/** 실제 날짜가 붙은 업무보고서. date 는 미팅한 날입니다. */
export interface MeetingReport extends MeetingReportSeed {
  /** YYYY-MM-DD */
  date: string
  /** 작성자의 구성원 번호. 고칠 수 있는 사람인지 이 값으로 가립니다. */
  ownerMemberId: string
  template: ReportTemplate
  /** 서버의 낙관적 잠금 버전. 합성 fallback에는 없을 수 있습니다. */
  version?: number
  currentSubmissionId?: string | null
  updatedAt?: string
}
