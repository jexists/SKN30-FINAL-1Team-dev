// 제출한 기간 보고서를 읽는 화면입니다. 미팅 보고서 상세와 같은 머리 띠·같은 두 열을 씁니다.
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { deleteReport } from '@/api/reportAgent'
import { errorMessage } from '@/api/errorMessage'
import { useCurrentUser } from '@/auth/sessionContext'
import AttachmentPanel from '@/components/AttachmentPanel'
import Button, { buttonClass } from '@/components/Button'
import ColumnHead from '@/components/ColumnHead'
import {
  CalendarIcon,
  DownloadIcon,
  EditIcon,
  SheetIcon,
  TeamIcon,
  TrashIcon,
} from '@/components/icons'
import Modal from '@/components/Modal'
import ReportBanner from '@/components/ReportBanner'
import ReportDocHeader from '@/components/ReportDocHeader'
import ReportView from '@/components/ReportView'
import { SkeletonDetail } from '@/components/Skeleton'
import { dailyComposePath, ROUTES } from '@/constants/routes'
import useTeamMembers from '@/hooks/useTeamMembers'
import { useReportDetail } from '@/shared/reportQuery'
import { isApprovedReportStatus } from '@/shared/reports'
import { showToast } from '@/shared/toast'
import { fmtDay, fmtDot, parseISO } from '@/utils/date'

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
  const { memberId, profile } = useCurrentUser()
  // 머리표가 쓰는 명부입니다. 작성자의 직책을 여기서 찾습니다 — 내 보고서든 남의
  // 보고서든 같은 길이라 예외를 두지 않습니다.
  const { members } = useTeamMembers()

  const navigate = useNavigate()
  // 삭제는 되돌릴 수 없으므로 한 번 물어봅니다.
  const [confirmingRemove, setConfirmingRemove] = useState(false)
  const [removing, setRemoving] = useState(false)

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
  // 지우는 것도 쓴 사람만 합니다. 서버도 남의 보고서에는 403 을 돌려줍니다.
  const mine = report.ownerMemberId === memberId
  const approved = isApprovedReportStatus(report.apiStatus)

  const removeReport = async () => {
    setRemoving(true)
    try {
      await deleteReport(report.id)
      showToast('보고서를 삭제했습니다.')
      setConfirmingRemove(false)
      navigate(ROUTES.DAILY)
    } catch (caught) {
      showToast(errorMessage(caught, '보고서를 삭제하지 못했습니다.'), { tone: 'error' })
    } finally {
      setRemoving(false)
    }
  }

  const day = parseISO(report.date)
  // 직책은 보고서에 실려 오지 않습니다. 명부에서 작성자를 찾아 채웁니다.
  const author = members.find((member) => member.id === report.ownerMemberId)
  const docTitle = `${report.period ?? fmtDay(day)} ${report.kind} 업무 보고서`

  return (
    <section>
      <h1 className="sr-only">{report.kind}업무보고 상세</h1>

      {/*
        머리 띠 하나가 어디에서 왔는지, 어느 기간의 보고서인지, 지금 어디까지 왔는지,
        그리고 이 문서로 할 수 있는 일을 함께 답니다. 작성 화면과 같은 띠입니다.

        잠긴 보고서에서도 버튼은 자리를 지킵니다. 사라진 버튼은 이유를 말해 주지
        못하므로, 누르면 왜 안 되는지를 알려 줍니다. 막는 것은 서버입니다.
      */}
      <ReportBanner
        /* 이 보고서가 놓인 탭으로 돌아갑니다. */
        crumb={<DailyListLink crumb tab={kindToPeriod(report.kind)} />}
        title={report.period ?? fmtDot(day)}
        kind={`${report.kind}업무보고`}
        badge={<ReportStatusBadge status={report.status} />}
        meta={[
          <>
            <CalendarIcon width={14} height={14} />
            {fmtDot(day)}
          </>,
          <>
            <TeamIcon width={14} height={14} />
            작성자 {report.owner}
          </>,
          <>
            <SheetIcon width={14} height={14} />
            보고 대상 {report.approver || '미지정'}
          </>,
        ]}
      >
        {editable ? (
          <Link
            className={buttonClass({ variant: 'outline' })}
            to={dailyComposePath(report.date, report.kind)}
          >
            <EditIcon width={15} height={15} />
            {report.apiStatus === 'draft' ? '이어서 작성' : '수정해서 다시 제출'}
          </Link>
        ) : (
          mine && (
            <Button
              type="button"
              variant="outline"
              onClick={() =>
                showToast(
                  approved
                    ? '확정된 보고서라 수정할 수 없습니다.'
                    : '제출이 끝나 수정할 수 없습니다.',
                  { tone: 'error' },
                )
              }
            >
              <EditIcon width={15} height={15} />
              수정하기
            </Button>
          )
        )}

        {mine && (
          <Button
            type="button"
            variant="outline"
            className={styles.danger}
            onClick={() => {
              if (approved) {
                showToast('확정된 보고서라 삭제할 수 없습니다.', { tone: 'error' })
                return
              }
              setConfirmingRemove(true)
            }}
          >
            <TrashIcon width={15} height={15} />
            삭제
          </Button>
        )}
      </ReportBanner>

      {/* 반려 사유는 문서가 아니라 문서에 붙은 말입니다. 작성 화면과 같이 면 밖에 섭니다. */}
      {report.reviewNote && (
        <article className={styles.review} role="note">
          <h2>반려 사유</h2>
          <p>{report.reviewNote}</p>
        </article>
      )}

      {/*
        결과물이 먼저입니다. 자료를 왼쪽에 놓는 것은 grid-template-areas 가 하고,
        DOM 순서는 건드리지 않습니다. 한 열로 접힐 때 긴 자료 아래에 보고서가 묻히면
        안 되고, 키보드 순서도 두 폭에서 같아야 합니다.
      */}
      <div className={styles.layout}>
        <div className={styles.report}>
          {/* 왼쪽 자료 열의 머리와 같은 줄에 섭니다. 작성 화면과도 같은 자리입니다. */}
          <ColumnHead title="보고서">
            {/* 이 문서를 종이로 내보내는 자리. 인쇄가 곧 PDF 입니다. */}
            <Button type="button" variant="outline" size="sm" onClick={() => window.print()}>
              <DownloadIcon width={15} height={15} />
              PDF 다운로드
            </Button>
          </ColumnHead>

          <article className={styles.card}>
            {/* 화면에서 읽는 양식지가 그대로 PDF 가 됩니다. 머리 띠는 조작부로만 남습니다. */}
            <ReportDocHeader
              title={docTitle}
              author={report.owner}
              jobTitle={author?.job_title ?? undefined}
              department={profile.department || report.department}
              company={profile.company || report.company}
              writtenOn={fmtDot(day)}
              approver={report.approver}
            />
            {/* 작성 화면과 같은 렌더러입니다. 같은 보고서가 두 모양으로 보이지 않게 합니다. */}
            <ReportView body={report.values.body ?? ''} />
          </article>
        </div>

        {/* 보고서를 쓸 때 근거로 삼은 것들. 짧은 것부터 둡니다. */}
        <aside className={styles.materials}>
          <ColumnHead title="보고서 자료" />

          <div className={styles.materialsBody}>
            <section className={styles.panel}>
              <h2 className={styles.panelTitle}>관련 보고서</h2>
              {/* 지금 다시 찾지 않습니다 — 제출 때 생성에 쓴 제출본만 줄로 섭니다. */}
              <ActivityList
                activities={report.activities}
                flush
                empty="작성 완료된 보고서가 없습니다."
                renderAside={(item) => {
                  const to = activityLink(item)
                  return to ? (
                    <Link className={buttonClass({ variant: 'outline', size: 'sm' })} to={to}>
                      보고서 확인
                    </Link>
                  ) : null
                }}
              />
            </section>

            <section className={styles.panel}>
              <h2 className={styles.panelTitle}>
                참고자료
                {report.attachments.length > 0 && (
                  <span className={styles.count}>{report.attachments.length}건</span>
                )}
              </h2>
              <AttachmentPanel
                attachments={report.attachments}
                reportId={report.id}
                readOnly
                gallery
              />
            </section>
          </div>
        </aside>
      </div>

      {confirmingRemove && (
        <Modal
          title="보고서를 삭제할까요?"
          description={`${report.period ?? fmtDot(day)} ${report.kind}업무보고가 목록에서 사라집니다.`}
          onClose={() => setConfirmingRemove(false)}
          onSubmit={removeReport}
          footer={
            <>
              <Button
                type="button"
                variant="outline"
                disabled={removing}
                onClick={() => setConfirmingRemove(false)}
              >
                취소
              </Button>
              <Button type="submit" variant="outline" className={styles.danger} disabled={removing}>
                {removing ? '삭제 중…' : '삭제'}
              </Button>
            </>
          }
        >
          <p className={styles.hint}>지운 보고서는 되살릴 수 없습니다.</p>
        </Modal>
      )}
    </section>
  )
}
