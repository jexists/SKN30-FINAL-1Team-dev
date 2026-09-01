// 목록 한 줄로 정규화한 보고서입니다.
//
// 업무 보고 화면은 일일·주간·월간 보고서와 업무보고서를 한 목록에서 봅니다.
// 두 타입이 겹치는 필드는 id·date·status·values·attachments 뿐이라 목록과 드로어가
// 매번 갈라지면 같은 코드를 두 벌 갖게 됩니다. 그래서 화면에 필요한 것만 여기서
// 한 모양으로 만들고, 아래쪽 컴포넌트는 이 타입 하나만 압니다.
import { dailyReportPath, meetingReportPath } from '@/constants/routes'
import type { DailyReport, MeetingReport, ReportStatus } from '@/types'

import { reportTitle } from './periods'

export interface ListRow {
  id: string
  /** YYYY-MM-DD */
  date: string
  /** 줄 앞의 종류 칩. '일일'·'주간'·'월간'·'미팅' */
  kindLabel: string
  title: string
  /** 드로어 본문에 한 문단으로 뜨는 요약 */
  summary: string
  /** 제목 아래 한 줄. 활동·첨부 건수이거나 메모입니다. */
  meta: string
  /** 오른쪽 끝 값. 일일은 보고 대상, 미팅은 고객사입니다. */
  aside: string
  status: ReportStatus
  /** 전문으로 넘어가는 경로 */
  to: string
  /** 검색이 훑을 글자. 소문자로 만들어 둡니다. */
  haystack: string
  /** 미팅만 갖습니다. 고객사 필터가 봅니다. */
  hospital?: string
  /** 이 보고서를 쓴 사람. 여러 사람이 섞여 보일 때만 화면에 섭니다. */
  author: string
}

const lower = (parts: (string | undefined)[]) => parts.filter(Boolean).join(' ').toLowerCase()

export function fromDailyReport(report: DailyReport): ListRow {
  // 저장 당시 양식의 첫 필드로 기존 보고서와 자유본문을 모두 표시합니다.
  const [first] = report.template.fields
  const files = report.attachments.length
  const acts = report.activities.filter((a) => a.included).length

  return {
    id: report.id,
    date: report.date,
    kindLabel: report.kind,
    title: reportTitle(report),
    summary: first ? (report.values[first.id]?.trim() ?? '') : '',
    meta:
      acts > 0 || files > 0
        ? `활동 ${acts}건${files > 0 ? ` · 첨부 ${files}건` : ''}`
        : report.note,
    aside: report.approver,
    author: report.owner,
    status: report.status,
    to: dailyReportPath(report.id),
    haystack: lower([
      reportTitle(report),
      report.note,
      report.approver,
      report.owner,
      report.kind,
      ...Object.values(report.values),
    ]),
  }
}

export function fromMeetingReport(report: MeetingReport): ListRow {
  const files = report.attachments.length
  const deal = report.salesDeal?.label
  const templateSummary = report.template.fields
    .map((field) => report.values[field.id]?.trim())
    .find(Boolean)

  return {
    id: report.id,
    date: report.date,
    kindLabel: '미팅',
    // 미팅 제목은 그 자리에서 정한 말이라 어느 병원인지가 붙어야 알아봅니다.
    title: [report.hospital, deal, report.title].filter(Boolean).join(' · '),
    summary:
      templateSummary ||
      report.values.body?.trim() ||
      report.values.reaction?.trim() ||
      report.values.note?.trim() ||
      '',
    meta: [`${report.time} · ${report.contact}`, files > 0 ? `첨부 ${files}건` : '']
      .filter(Boolean)
      .join(' · '),
    aside: report.hospital,
    author: report.owner,
    status: report.status,
    to: meetingReportPath(report.id),
    haystack: lower([
      report.hospital,
      report.title,
      deal,
      report.owner,
      report.dept,
      report.contact,
      report.product,
      report.place,
      report.transcript,
      ...Object.values(report.values),
    ]),
    hospital: report.hospital,
  }
}

/** 최근 것이 위로. 두 종류를 합친 뒤 늘 이 순서로 세웁니다. */
export const byDateDesc = (a: ListRow, b: ListRow) => b.date.localeCompare(a.date)
