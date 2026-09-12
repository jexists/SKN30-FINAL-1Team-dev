// 제출한 기간 보고서를 읽는 화면입니다. 미팅 보고서 상세와 같은 머리 띠·같은 두 열을 씁니다.
import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router'

import { useCurrentUser } from '@/auth/sessionContext'
import AttachmentPanel from '@/components/AttachmentPanel'
import Button, { buttonClass } from '@/components/Button'
import {
  CalendarIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  DownloadIcon,
  EditIcon,
  SheetIcon,
  TeamIcon,
} from '@/components/icons'
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
import { canEditPeriodReport, toReport, useRelatedReports } from './useDailyReports'

import styles from './Detail.module.scss'

export default function Detail() {
  const { reportId } = useParams()
  const { item, loading, error, reload } = useReportDetail(
    reportId,
    '보고서를 불러오지 못했습니다.',
  )

  const report = item ? toReport(item) : undefined
  const related = useRelatedReports(report?.kind ?? '일일', report?.date ?? '', !!report)
  // 보고서는 쓴 사람만 고칩니다. 팀장이 팀원의 보고서를 열어도 고치는 길은 서지 않습니다.
  const { memberId } = useCurrentUser()

  // 작성 화면과 같은 손잡이입니다. 보고서만 넓게 읽고 싶을 때 자료 열을 접습니다.
  const [materialsCollapsed, setMaterialsCollapsed] = useState(false)
  // 접으면 누른 손잡이가 화면에서 사라집니다. 남는 쪽 손잡이로 초점을 넘겨 줍니다.
  const collapseRef = useRef<HTMLButtonElement>(null)
  const expandRef = useRef<HTMLButtonElement>(null)
  const toggledRef = useRef(false)
  useEffect(() => {
    if (!toggledRef.current) return
    ;(materialsCollapsed ? expandRef : collapseRef).current?.focus()
  }, [materialsCollapsed])

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
  const day = parseISO(report.date)

  return (
    <section>
      <h1 className="sr-only">{report.kind}업무보고 상세</h1>

      {/*
        머리 띠 하나가 어디에서 왔는지, 어느 기간의 보고서인지, 지금 어디까지 왔는지,
        그리고 이 문서로 할 수 있는 일을 함께 답니다.
      */}
      <header className={styles.banner}>
        <div className={styles.heading}>
          {/* 이 보고서가 놓인 탭으로 돌아갑니다. */}
          <DailyListLink crumb tab={kindToPeriod(report.kind)} />

          <p className={styles.title}>
            {report.period ?? fmtDot(day)}
            <span>{report.kind}업무보고</span>
            <ReportStatusBadge status={report.status} />
          </p>

          <p className={styles.meta}>
            <span className={styles.metaItem}>
              <CalendarIcon width={14} height={14} />
              <span className={styles.when}>{fmtDot(day)}</span>
            </span>
            <span className={`${styles.bar} ${styles.breakBar}`} aria-hidden="true" />
            <span className={styles.metaItem}>
              <TeamIcon width={14} height={14} />
              작성자 {report.owner}
            </span>
            <span className={styles.bar} aria-hidden="true" />
            <span className={styles.metaItem}>
              <SheetIcon width={14} height={14} />
              보고 대상 {report.approver}
            </span>
          </p>
        </div>

        <div className={styles.actions}>
          {editable ? (
            <Link
              className={buttonClass({ variant: 'outline' })}
              to={dailyComposePath(report.date, report.kind)}
            >
              <EditIcon width={15} height={15} />
              {report.apiStatus === 'draft' ? '이어서 작성' : '수정해서 다시 제출'}
            </Link>
          ) : (
            <span className={styles.sealed}>제출이 끝나 수정할 수 없습니다</span>
          )}

          {/* 작성 화면과 같은 버튼입니다. 인쇄가 곧 PDF 입니다. */}
          <Button type="button" onClick={() => window.print()}>
            <DownloadIcon width={15} height={15} />
            PDF 다운로드
          </Button>
        </div>
      </header>

      {/*
        결과물이 먼저입니다. 자료를 왼쪽에 놓는 것은 grid-template-areas 가 하고,
        DOM 순서는 건드리지 않습니다. 한 열로 접힐 때 긴 자료 아래에 보고서가 묻히면
        안 되고, 키보드 순서도 두 폭에서 같아야 합니다.
      */}
      <div
        className={
          materialsCollapsed ? `${styles.layout} ${styles.materialsCollapsed}` : styles.layout
        }
      >
        <div className={styles.report}>
          {report.reviewNote && (
            <article className={styles.review} role="note">
              <h2>반려 사유</h2>
              <p>{report.reviewNote}</p>
            </article>
          )}

          <article className={styles.card}>
            <h2 className={styles.docTitle}>보고 내용</h2>
            <ReportFields template={report.template} values={report.values} readOnly />
          </article>
        </div>

        {/* 보고서를 쓸 때 근거로 삼은 것들. 짧은 것부터 둡니다. */}
        <aside
          id="period-detail-materials"
          className={
            materialsCollapsed ? `${styles.materials} ${styles.collapsed}` : styles.materials
          }
        >
          {/* 판의 머리는 접어도 남습니다. 한 열로 접히는 폭에서는 여기가 여닫이입니다. */}
          <div className={styles.materialHead}>
            <h2>관련 보고서</h2>
            <Button
              type="button"
              variant="outline"
              size="sm"
              iconOnly
              ref={collapseRef}
              className={styles.collapseAction}
              aria-expanded
              aria-controls="period-detail-materials"
              aria-label="관련 자료 접기"
              onClick={() => {
                toggledRef.current = true
                setMaterialsCollapsed(true)
              }}
            >
              <ChevronLeftIcon width={15} height={15} />
            </Button>
            <button
              type="button"
              className={styles.mobileToggle}
              aria-expanded={!materialsCollapsed}
              aria-controls="period-detail-materials-body"
              aria-label={materialsCollapsed ? '관련 자료 펼치기' : '관련 자료 접기'}
              onClick={() => setMaterialsCollapsed((collapsed) => !collapsed)}
            >
              <ChevronDownIcon width={16} height={16} aria-hidden="true" />
            </button>
          </div>

          <div id="period-detail-materials-body" className={styles.materialsBody}>
            <section>
              {related.loading ? (
                <p role="status">관련 보고서를 불러오는 중입니다.</p>
              ) : related.error ? (
                <>
                  <p role="alert">{related.error}</p>
                  <Button variant="outline" onClick={related.reload}>
                    다시 시도
                  </Button>
                </>
              ) : (
                <ActivityList
                  activities={related.activities}
                  renderAside={(item) => {
                    const to = activityLink(item)
                    return to ? <Link to={to}>원본 보기</Link> : null
                  }}
                />
              )}
            </section>

            <section>
              <h2 className={styles.materialHead}>
                참고자료
                {report.attachments.length > 0 && (
                  <span className={styles.count}>{report.attachments.length}건</span>
                )}
              </h2>
              <AttachmentPanel attachments={report.attachments} reportId={report.id} readOnly />
            </section>
          </div>
        </aside>

        {/* 접으면 판째로 사라지므로 펼치는 손잡이만 화면 왼쪽에 남습니다. */}
        {materialsCollapsed && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            iconOnly
            ref={expandRef}
            className={styles.materialsToggle}
            aria-expanded={false}
            aria-controls="period-detail-materials"
            aria-label="관련 자료 펼치기"
            onClick={() => {
              toggledRef.current = true
              setMaterialsCollapsed(false)
            }}
          >
            <ChevronRightIcon width={15} height={15} />
          </Button>
        )}
      </div>
    </section>
  )
}
