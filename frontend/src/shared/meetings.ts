// 미팅보고서 도메인. 양식과 시드는 mocks/ 에서 받습니다.
import { meetingReportSeed, meetingTemplate } from '@/mocks'
import type { MeetingReport, ReportActivity } from '@/types'
import { addDays, iso, TODAY } from '@/utils/date'

export { meetingTemplate }

export const meetingReportHistory: MeetingReport[] = meetingReportSeed
  .map((seed) => ({ ...seed, date: iso(addDays(TODAY, seed.off)) }))
  .sort((a, b) => b.date.localeCompare(a.date))

/**
 * 확정된 미팅 기록을 일일보고의 활동 한 줄로 바꿉니다.
 * 작성 중인 기록은 아직 일어난 일로 볼 수 없어 빼고 넘깁니다.
 */
export function meetingActivitiesFor(reports: MeetingReport[]): ReportActivity[] {
  return reports
    .filter((report) => report.status === '확정')
    .map((report) => ({
      id: `meet-${report.id}`,
      source: '미팅보고서',
      title: `${report.hospital} ${report.title}`,
      desc: report.values.decision?.split('\n')[0] || '미팅 기록 확정',
      included: true,
    }))
}
