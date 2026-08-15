import { Link, useParams } from 'react-router'

import AttachmentPanel from '@/components/AttachmentPanel'
import { ChevronLeftIcon } from '@/components/icons'
import ReportFields from '@/components/ReportFields'
import { dailyComposePath, ROUTES } from '@/constants/routes'
import { templateFor } from '@/shared/reports'
import { fmtDot, parseISO } from '@/utils/date'

import ActivityList from './components/ActivityList'
import ReportStatusBadge from './components/ReportStatusBadge'
import useDailyReports from './useDailyReports'

import styles from './Detail.module.scss'

export default function Detail() {
  const { reportId } = useParams()
  const { findReport } = useDailyReports()

  const report = reportId ? findReport(reportId) : undefined

  if (!report) {
    return (
      <section>
        <h1 className="sr-only">보고서를 찾을 수 없음</h1>
        <p className={styles.missing}>
          보고서를 찾을 수 없습니다. <Link to={ROUTES.DAILY}>업무 보고로 돌아가기</Link>
        </p>
      </section>
    )
  }

  return (
    <section>
      <h1 className="sr-only">{report.kind}업무보고 상세</h1>

      <header className={styles.head}>
        <Link className={styles.back} to={ROUTES.DAILY}>
          <ChevronLeftIcon />
          업무 보고
        </Link>
        <p className={styles.date}>{report.period ?? fmtDot(parseISO(report.date))}</p>
        <ReportStatusBadge status={report.status} />
        <span className={styles.approver}>보고 대상 {report.approver}</span>

        {report.status === '반려' && (
          <Link className={styles.rewrite} to={dailyComposePath(report.date, report.kind)}>
            수정해서 다시 제출
          </Link>
        )}
      </header>

      <div className={styles.panels}>
        <article className={styles.panel}>
          <h2>보고 내용</h2>
          <ReportFields template={templateFor(report.kind)} values={report.values} readOnly />
        </article>

        <article className={styles.panel}>
          <h2>포함된 활동</h2>
          <ActivityList activities={report.activities} readOnly />
        </article>

        <article className={styles.panel}>
          <h2>첨부 자료</h2>
          <AttachmentPanel attachments={report.attachments} readOnly />
        </article>
      </div>
    </section>
  )
}
