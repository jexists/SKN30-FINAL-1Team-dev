// 제출한 미팅 기록을 읽는 화면입니다. 작성 화면과 같은 컴포넌트를 읽기 모드로 씁니다.
import { Link, useParams } from 'react-router'

import { useCurrentUser } from '@/auth/sessionContext'
import AttachmentPanel from '@/components/AttachmentPanel'
import Button, { buttonClass } from '@/components/Button'
import { EditIcon } from '@/components/icons'
import ReportFields from '@/components/ReportFields'
import { SkeletonDetail } from '@/components/Skeleton'
import StatusBadge from '@/components/StatusBadge'
import { meetingComposePath, ROUTES } from '@/constants/routes'
import DailyListLink from '@/pages/Daily/components/DailyListLink'
import { useReportDetail } from '@/shared/reportQuery'
import { fmtDay, parseISO } from '@/utils/date'

import MeetingFacts from './components/MeetingFacts'
import MeetingSharedPanel from './components/MeetingSharedPanel'
import { REVIEW_LABEL, REVIEW_TONE } from './reviewStatus'
import { toMeetingReport } from './useMeetingReports'

import styles from './Detail.module.scss'

export default function Detail() {
  const { reportId } = useParams()
  const { item, loading, error, reload } = useReportDetail(
    reportId,
    '업무보고서를 불러오지 못했습니다.',
  )

  const report = item ? toMeetingReport(item) : undefined
  // 보고서는 쓴 사람만 고칩니다. 팀장이 팀원의 보고서를 열어도 고치는 길은 서지 않습니다.
  const { memberId } = useCurrentUser()
  const isMine = report?.ownerMemberId === memberId

  if (loading)
    return (
      <section>
        <SkeletonDetail label="업무보고서를 불러오는 중입니다." title height={420} />
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
        <h1 className="sr-only">업무보고서를 찾을 수 없음</h1>
        <p className={styles.missing}>
          업무보고서를 찾을 수 없습니다. <Link to={ROUTES.DASHBOARD}>대시보드로 돌아가기</Link>
        </p>
      </section>
    )
  }

  const editable = report.apiStatus === 'draft' || report.apiStatus === 'changes_requested'

  return (
    <section>
      <h1 className="sr-only">
        {report.hospital} {report.title} 업무보고서
      </h1>

      {/* 미팅 기록에서 나가므로 목록도 업무보고서 탭으로 엽니다. */}
      <DailyListLink back tab="meeting" className={styles.toDaily} />

      {/*
        머리말은 어느 회사의 언제 기록인지와 지금 어디까지 왔는지만 말합니다.
        미팅 제목은 오른쪽 보고서의 머리글이 이미 크게 달고 있어 여기서 뺐습니다.
      */}
      <header className={styles.head}>
        <div className={styles.heading}>
          <p className={styles.title}>
            {report.hospital}
            {report.salesDeal && <span>{report.salesDeal.label}</span>}
            <StatusBadge label={REVIEW_LABEL[report.review]} tone={REVIEW_TONE[report.review]} />
          </p>

          <p className={styles.meta}>
            <span className={styles.when}>
              {fmtDay(parseISO(report.date))} {report.time}
            </span>
            <span className={styles.dot} aria-hidden="true">
              ·
            </span>
            <span>작성자 {report.owner}</span>
          </p>
          {(report.assessment || report.analysisError) && (
            <p className={styles.meta}>
              <span
                title={
                  report.analysisError ??
                  (report.assessment ? `ML 모델 ${report.assessment.model_version}` : undefined)
                }
              >
                <StatusBadge
                  label={
                    report.analysisError
                      ? 'ML 분석 실패'
                      : `${report.assessment!.label === 'high' ? '성사 가능성 높음' : '관찰 필요'} · ${Math.round(report.assessment!.high_probability * 100)}%`
                  }
                  tone={
                    report.analysisError
                      ? 'red'
                      : report.assessment!.label === 'high'
                        ? 'green'
                        : 'orange'
                  }
                />
              </span>
              {report.analysisError && <span>{report.analysisError}</span>}
            </p>
          )}
        </div>
      </header>

      {/*
        결과물이 먼저입니다. 자료를 왼쪽에 놓는 것은 grid-template-areas 가 하고,
        DOM 순서는 건드리지 않습니다. 좁은 화면에서 한 열로 접힐 때 긴 미팅 내용
        아래에 보고서가 묻히면 안 되고, 키보드 순서도 두 폭에서 같아야 합니다.
      */}
      <div className={styles.layout}>
        <div className={styles.report}>
          <MeetingSharedPanel shared={report.meetingShared ?? null} />
          <article className={styles.sheet}>
            <h2 className={styles.docTitle}>{report.title}</h2>
            <p className={styles.docWhen}>
              {fmtDay(parseISO(report.date))} {report.time}
            </p>

            {report.template.fields.length === 0 ? (
              <p role="alert">저장된 보고서 양식 필드를 해석할 수 없습니다.</p>
            ) : (
              <ReportFields template={report.template} values={report.values} readOnly />
            )}
            {report.evidence && <p className={styles.evidence}>{report.evidence}</p>}
          </article>

          {/*
            고치는 것은 다 읽은 다음의 일입니다. 머리말에서 먼저 소리치지 않고
            보고서 끝에서 기다립니다. 작성 화면도 제출 버튼이 시트 아래에 있습니다.
          */}
          <div className={styles.docActions}>
            {/* 작성 화면과 같은 자리, 같은 버튼입니다. 인쇄가 곧 PDF 입니다. */}
            <Button variant="outline" type="button" onClick={() => window.print()}>
              PDF 다운로드
            </Button>

            {!editable ? (
              <span className={`${styles.sealed} ${styles.trailing}`}>
                {report.review === 'approved'
                  ? '팀장 확인이 끝나 수정할 수 없습니다'
                  : '현재 상태에서는 수정할 수 없습니다'}
              </span>
            ) : isMine ? (
              <Link
                className={buttonClass({}, styles.trailing)}
                to={meetingComposePath(report.agendaId)}
              >
                <EditIcon width={15} height={15} />
                수정하기
              </Link>
            ) : null}
          </div>
        </div>

        {/* 보고서를 쓸 때 낸 것들. 짧은 것부터 두고, 길이가 정해지지 않은 미팅 내용이 끝입니다. */}
        <aside className={styles.materials}>
          <section>
            <h2 className={styles.materialHead}>미팅 정보</h2>
            <MeetingFacts dept={report.dept} contact={report.contact} place={report.place} />
          </section>

          <section>
            <h2 className={styles.materialHead}>
              첨부 자료
              {report.attachments.length > 0 && (
                <span className={styles.count}>{report.attachments.length}건</span>
              )}
            </h2>
            <AttachmentPanel attachments={report.attachments} readOnly />
          </section>

          {report.transcript && (
            <section>
              <h2 className={styles.materialHead}>미팅 내용</h2>
              <p className={styles.transcript}>{report.transcript}</p>
            </section>
          )}
        </aside>
      </div>
    </section>
  )
}
