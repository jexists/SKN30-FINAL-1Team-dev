import { Link, useParams } from 'react-router'

import { useCurrentUser } from '@/auth/sessionContext'
import AttachmentPanel from '@/components/AttachmentPanel'
import Button from '@/components/Button'
import ReportFields from '@/components/ReportFields'
import { SkeletonDetail } from '@/components/Skeleton'
import { dailyComposePath, ROUTES } from '@/constants/routes'
import { useReportDetail } from '@/shared/reportQuery'
import { fmtDot, parseISO } from '@/utils/date'

import ActivityList from './components/ActivityList'
import DailyListLink from './components/DailyListLink'
import ReportStatusBadge from './components/ReportStatusBadge'
import { kindToPeriod } from './periods'
import { activityLink } from './sources'
import { canEditPeriodReport, toReport } from './useDailyReports'

import styles from './Detail.module.scss'

export default function Detail() {
  const { reportId } = useParams()
  const { item, loading, error, reload } = useReportDetail(
    reportId,
    '보고서를 불러오지 못했습니다.',
  )

  const report = item ? toReport(item) : undefined
  // 보고서는 쓴 사람만 고칩니다. 팀장이 팀원의 보고서를 열어도 고치는 길은 서지 않습니다.
  const { memberId } = useCurrentUser()

  if (loading)
    return (
      <section>
        <SkeletonDetail label="보고서를 불러오는 중입니다." title height={420} />
      </section>
    )

  if (error) {
    return (
      <section>
        <p className={styles.missing} role="alert">
          {error}
        </p>
        <Button variant="outline" onClick={reload}>
          다시 시도
        </Button>
      </section>
    )
  }

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

  const editable = canEditPeriodReport(report, memberId)

  return (
    <section>
      <h1 className="sr-only">{report.kind}업무보고 상세</h1>

      {/* 이 보고서가 놓인 탭으로 돌아갑니다. */}
      <DailyListLink back tab={kindToPeriod(report.kind)} className={styles.back} />

      <header className={styles.head}>
        <p className={styles.date}>{report.period ?? fmtDot(parseISO(report.date))}</p>
        <ReportStatusBadge status={report.status} />
        <span className={styles.approver}>보고 대상 {report.approver}</span>

        {editable && (
          <Link className={styles.rewrite} to={dailyComposePath(report.date, report.kind)}>
            {report.apiStatus === 'draft' ? '이어서 작성' : '수정해서 다시 제출'}
          </Link>
        )}
      </header>

      <div className={styles.panels}>
        {report.reviewNote && (
          <article className={`${styles.panel} ${styles.review}`} role="note">
            <h2>반려 사유</h2>
            <p>{report.reviewNote}</p>
          </article>
        )}

        <article className={styles.panel}>
          <h2>보고 내용</h2>
          <ReportFields template={report.template} values={report.values} readOnly />
        </article>

        <article className={styles.panel}>
          <h2>포함된 활동</h2>
          {/* 무엇을 근거로 썼는지 되짚을 수 있게 원본 보고서로 가는 길을 답니다. */}
          <ActivityList
            activities={report.activities}
            readOnly
            renderAside={(item) => {
              const to = activityLink(item)
              return to ? <Link to={to}>원본 보기</Link> : null
            }}
          />
        </article>

        <article className={styles.panel}>
          <h2>첨부 자료</h2>
          <AttachmentPanel attachments={report.attachments} readOnly />
        </article>
      </div>
    </section>
  )
}
