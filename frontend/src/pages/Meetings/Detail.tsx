// 확정한 미팅 기록을 읽는 화면입니다. 작성 화면과 같은 컴포넌트를 읽기 모드로 씁니다.
import { Link, useParams } from 'react-router'

import AttachmentPanel from '@/components/AttachmentPanel'
import Button from '@/components/Button'
import { ChevronLeftIcon } from '@/components/icons'
import ReportFields from '@/components/ReportFields'
import { meetingComposePath, ROUTES } from '@/constants/routes'
import { fmtDay, parseISO } from '@/utils/date'

import MeetingFacts from './components/MeetingFacts'
import useMeetingReports from './useMeetingReports'

import styles from './Detail.module.scss'

export default function Detail() {
  const { reportId } = useParams()
  const { findReport, loading, error, reload } = useMeetingReports()

  const report = reportId ? findReport(reportId) : undefined

  if (loading)
    return (
      <p className={styles.missing} role="status">
        미팅보고서를 불러오는 중입니다.
      </p>
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
        <h1 className="sr-only">미팅보고서를 찾을 수 없음</h1>
        <p className={styles.missing}>
          미팅보고서를 찾을 수 없습니다. <Link to={ROUTES.DASHBOARD}>대시보드로 돌아가기</Link>
        </p>
      </section>
    )
  }

  return (
    <section>
      <h1 className="sr-only">
        {report.hospital} {report.title} 미팅보고서
      </h1>

      <header className={styles.head}>
        <Link className={styles.back} to={ROUTES.DASHBOARD}>
          <ChevronLeftIcon />
          대시보드
        </Link>

        <p className={styles.title}>
          {report.hospital}
          <span className={styles.subject}>{report.title}</span>
        </p>

        <span className={styles.when}>
          {fmtDay(parseISO(report.date))} {report.time}
        </span>

        {/* 확정이 기본이라 그때는 굳이 말하지 않고, 아직 쓰는 중일 때만 알립니다. */}
        {report.status !== '확정' && <span className={styles.status}>{report.status}</span>}

        <Link className={styles.rewrite} to={meetingComposePath(report.agendaId)}>
          기록 수정
        </Link>
      </header>

      <div className={styles.panels}>
        <article className={styles.panel}>
          <h2>미팅 정보</h2>
          <MeetingFacts
            dept={report.dept}
            contact={report.contact}
            product={report.product}
            place={report.place}
          />
        </article>

        <article className={styles.panel}>
          <h2>구조화 결과</h2>
          {report.template.fields.length === 0 ? (
            <p role="alert">저장된 보고서 양식 필드를 해석할 수 없습니다.</p>
          ) : (
            <ReportFields template={report.template} values={report.values} readOnly />
          )}
          {report.evidence && <p className={styles.evidence}>{report.evidence}</p>}
        </article>

        {report.transcript && (
          <article className={styles.panel}>
            <h2>미팅 내용</h2>
            <p className={styles.transcript}>{report.transcript}</p>
          </article>
        )}

        <article className={styles.panel}>
          <h2>첨부 자료</h2>
          <AttachmentPanel attachments={report.attachments} readOnly />
        </article>
      </div>
    </section>
  )
}
