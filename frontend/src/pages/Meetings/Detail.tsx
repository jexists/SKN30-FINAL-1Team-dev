// 제출한 미팅 기록을 읽는 화면입니다. 작성 화면과 같은 컴포넌트를 읽기 모드로 씁니다.
import { useId, useState } from 'react'
import { Link, useParams } from 'react-router'

import { useCurrentUser } from '@/auth/sessionContext'
import AttachmentPanel from '@/components/AttachmentPanel'
import Button, { buttonClass } from '@/components/Button'
import {
  CalendarIcon,
  CheckIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  DownloadIcon,
  EditIcon,
  SheetIcon,
  TeamIcon,
} from '@/components/icons'
import ReportBody from '@/components/ReportBody'
import { SkeletonDetail } from '@/components/Skeleton'
import StatusBadge, { type StatusTone } from '@/components/StatusBadge'
import { meetingComposePath, ROUTES } from '@/constants/routes'
import RecordDrawer from '@/pages/Dashboard/components/RecordDrawer'
import DailyListLink from '@/pages/Daily/components/DailyListLink'
import { useAgendaItem } from '@/shared/agenda'
import { useReportDetail } from '@/shared/reportQuery'
import { isAuthorEditableReportStatus } from '@/shared/reports'
import { fmtDay, parseISO } from '@/utils/date'
import { meetingAttachmentPurposeOf } from '@/utils/attachment'
import type { MeetingDealSection } from '@/types'

import DealCardHeader from './components/DealCardHeader'
import MeetingFacts from './components/MeetingFacts'
import MeetingSharedPanel from './components/MeetingSharedPanel'
import { isInsufficientDealPrediction } from './generatedDraft'
import { MEETING_STATUS_TONE, meetingStatusLabel } from './reviewStatus'
import { toMeetingReport } from './useMeetingReports'

import styles from './Detail.module.scss'

function assessmentBadge(section: MeetingDealSection): {
  label: string
  tone: StatusTone
  title?: string
} {
  if (section.analysisStatus === 'pending') {
    return { label: 'ML 분석 중', tone: 'blue' }
  }
  if (isInsufficientDealPrediction(section.analysisError)) {
    return { label: '판단 정보 부족', tone: 'neutral' }
  }
  if (section.analysisError) {
    return { label: 'ML 분석 실패', tone: 'red', title: section.analysisError }
  }
  if (!section.assessment) return { label: 'ML 분석 결과 없음', tone: 'neutral' }
  const probability = `${Math.round(section.assessment.high_probability * 100)}%`
  return section.assessment.label === 'high'
    ? {
        label: `성사 가능성 높음 · ${probability}`,
        tone: 'green',
        title: `ML 모델 ${section.assessment.model_version}`,
      }
    : {
        label: `관찰 필요 · ${probability}`,
        tone: 'orange',
        title: `ML 모델 ${section.assessment.model_version}`,
      }
}

/*
 * 딜 한 건의 보고서. 작성 화면의 딜 카드와 같은 머리를 씁니다.
 */
function DealSectionCard({
  section,
  fallbackTitle,
}: {
  section: MeetingDealSection
  fallbackTitle: string
}) {
  const titleId = useId()

  return (
    <article className={styles.card} aria-labelledby={titleId}>
      <DealCardHeader
        dealId={section.salesDealId}
        label={section.salesDeal.label}
        note={section.salesDeal.note}
        badge={assessmentBadge(section)}
      />

      <div className={styles.cardBody}>
        {/* 미팅일은 머리 띠에, 제품은 딜 머리에 이미 있습니다. 여기는 제목만입니다. */}
        <h2 className={styles.docTitle} id={titleId}>
          {section.title || fallbackTitle}
        </h2>

        {section.values.body?.trim() ? (
          <ReportBody className={styles.reportBody} body={section.values.body} />
        ) : (
          <p className={styles.emptyBody}>작성된 내용이 없습니다.</p>
        )}
        {section.evidence && <p className={styles.evidence}>{section.evidence}</p>}
        {section.analysisError && !isInsufficientDealPrediction(section.analysisError) && (
          <p className={styles.sectionError} role="status">
            ML 분석: {section.analysisError}
          </p>
        )}
        {section.reportError && (
          <p className={styles.sectionError} role="status">
            보고서 생성: {section.reportError}
          </p>
        )}
      </div>
    </article>
  )
}

export default function Detail() {
  const { reportId } = useParams()
  const { item, loading, error, reload } = useReportDetail(
    reportId,
    '미팅 보고서를 불러오지 못했습니다.',
  )

  const report = item ? toMeetingReport(item) : undefined
  // 보고서는 쓴 사람만 고칩니다. 팀장이 팀원의 보고서를 열어도 고치는 길은 서지 않습니다.
  const { memberId } = useCurrentUser()
  const isMine = report?.ownerMemberId === memberId
  // 작성 화면과 같은 손잡이입니다. 보고서만 넓게 읽고 싶을 때 자료 열을 접습니다.
  const [materialsCollapsed, setMaterialsCollapsed] = useState(false)
  // 자세히 보기는 작성 화면과 같은 드로어입니다. 일정 원본은 보고서에 없어 따로 받아 옵니다.
  const [detailOpen, setDetailOpen] = useState(false)
  const agenda = useAgendaItem(report?.agendaId ?? '')

  if (loading)
    return (
      <section>
        <SkeletonDetail label="미팅 보고서를 불러오는 중입니다." title height={420} />
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
        <h1 className="sr-only">미팅 보고서를 찾을 수 없음</h1>
        <p className={styles.missing}>
          미팅 보고서를 찾을 수 없습니다. <Link to={ROUTES.DASHBOARD}>대시보드로 돌아가기</Link>
        </p>
      </section>
    )
  }

  const editable = isAuthorEditableReportStatus(report.apiStatus)
  const meetingDay = parseISO(report.date)

  return (
    <section>
      <h1 className="sr-only">
        {report.hospital} {report.title} 미팅 보고서
      </h1>

      {/*
        머리 띠 하나가 어디에서 왔는지, 어느 회사의 언제 기록인지, 지금 어디까지
        왔는지, 그리고 이 문서로 할 수 있는 일을 함께 답니다. 미팅 제목은 오른쪽
        보고서의 머리글이 이미 크게 달고 있어 여기서는 회사 옆에 붙여만 둡니다.
      */}
      <header className={styles.banner}>
        <div className={styles.heading}>
          {/* 미팅 기록에서 나가므로 목록도 미팅 보고서 탭으로 엽니다. */}
          <DailyListLink crumb tab="meeting" />

          <p className={styles.title}>
            {report.hospital}
            {report.title && <span>{report.title}</span>}
            <StatusBadge
              label={meetingStatusLabel(report.apiStatus ?? 'draft')}
              tone={MEETING_STATUS_TONE[meetingStatusLabel(report.apiStatus ?? 'draft')]}
              icon={<CheckIcon width={12} height={12} />}
            />
          </p>

          <p className={styles.meta}>
            <span className={styles.metaItem}>
              <CalendarIcon width={14} height={14} />
              <span className={styles.when}>
                {meetingDay.getFullYear()}년 {fmtDay(meetingDay)} {report.time}
              </span>
            </span>
            <span className={`${styles.bar} ${styles.breakBar}`} aria-hidden="true" />
            <span className={styles.metaItem}>
              <TeamIcon width={14} height={14} />
              작성자 {report.owner}
            </span>
            <span className={styles.bar} aria-hidden="true" />
            <span className={styles.metaItem}>
              <SheetIcon width={14} height={14} />
              {report.dealSections.length > 0
                ? `총 ${report.dealSections.length}건`
                : '관련 딜 없음'}
            </span>
          </p>
        </div>

        <div className={styles.actions}>
          {/* 잠그는 것은 서버입니다(approved 는 더 이상 고칠 수 없습니다). */}
          {!editable ? (
            <span className={styles.sealed}>작성이 완료되어 수정할 수 없습니다</span>
          ) : isMine ? (
            <Link
              className={buttonClass({ variant: 'outline' })}
              to={meetingComposePath(report.agendaId)}
            >
              <EditIcon width={15} height={15} />
              수정하기
            </Link>
          ) : null}

          {/* 작성 화면과 같은 버튼입니다. 인쇄가 곧 PDF 입니다. */}
          <Button type="button" onClick={() => window.print()}>
            <DownloadIcon width={15} height={15} />
            PDF 다운로드
          </Button>
        </div>
      </header>

      {/*
        결과물이 먼저입니다. 자료를 왼쪽에 놓는 것은 grid-template-areas 가 하고,
        DOM 순서는 건드리지 않습니다. 좁은 화면에서 한 열로 접힐 때 긴 미팅 내용
        아래에 보고서가 묻히면 안 되고, 키보드 순서도 두 폭에서 같아야 합니다.
      */}
      <div
        className={
          materialsCollapsed ? `${styles.layout} ${styles.materialsCollapsed}` : styles.layout
        }
      >
        <div className={styles.report}>
          <MeetingSharedPanel shared={report.meetingShared ?? null} />
          {report.dealSections.length === 0 ? (
            !report.meetingShared && <p className={styles.emptySections}>작성된 내용이 없습니다.</p>
          ) : (
            <div className={styles.dealSections}>
              {report.dealSections.map((section, index) => (
                <DealSectionCard
                  key={`deal-report-${section.salesDealId}-${index}`}
                  section={section}
                  fallbackTitle={report.title}
                />
              ))}
            </div>
          )}
        </div>

        {/* 보고서를 쓸 때 낸 것들. 짧은 것부터 두고, 길이가 정해지지 않은 미팅 내용이 끝입니다. */}
        <aside
          id="detail-materials"
          className={
            materialsCollapsed ? `${styles.materials} ${styles.collapsed}` : styles.materials
          }
        >
          {/* 판의 머리는 접어도 남습니다. 한 열로 접히는 폭에서는 여기가 여닫이입니다. */}
          <div className={styles.materialHead}>
            <h2>미팅 정보</h2>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!agenda.item}
              onClick={() => setDetailOpen(true)}
            >
              자세히 보기
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              iconOnly
              className={styles.collapseAction}
              aria-expanded
              aria-controls="detail-materials"
              aria-label="미팅 자료 접기"
              onClick={() => setMaterialsCollapsed(true)}
            >
              <ChevronLeftIcon width={15} height={15} />
            </Button>
            <button
              type="button"
              className={styles.mobileToggle}
              aria-expanded={!materialsCollapsed}
              aria-controls="detail-materials-body"
              aria-label={materialsCollapsed ? '미팅 자료 펼치기' : '미팅 자료 접기'}
              onClick={() => setMaterialsCollapsed((collapsed) => !collapsed)}
            >
              <ChevronDownIcon width={16} height={16} aria-hidden="true" />
            </button>
          </div>

          <div id="detail-materials-body" className={styles.materialsBody}>
            <section>
              <MeetingFacts dept={report.dept} contact={report.contact} place={report.place} />
            </section>

            {(
              [
                ['미팅 원문 파일', 'meeting_source'],
                ['참고자료', 'reference'],
              ] as const
            ).map(([label, purpose]) => {
              const attachments = report.attachments.filter(
                (attachment) => meetingAttachmentPurposeOf(attachment) === purpose,
              )
              return (
                <section key={purpose}>
                  <h2 className={styles.materialHead}>
                    {label}
                    {attachments.length > 0 && (
                      <span className={styles.count}>{attachments.length}건</span>
                    )}
                  </h2>
                  <AttachmentPanel attachments={attachments} reportId={report.id} readOnly />
                </section>
              )
            })}

            {report.transcript && (
              <section>
                <h2 className={styles.materialHead}>미팅 내용</h2>
                <p className={styles.transcript}>{report.transcript}</p>
              </section>
            )}
          </div>
        </aside>

        {/* 접으면 판째로 사라지므로 펼치는 손잡이만 화면 왼쪽 아래에 남습니다. */}
        {materialsCollapsed && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            iconOnly
            className={styles.materialsToggle}
            aria-expanded={false}
            aria-controls="detail-materials"
            aria-label="미팅 자료 펼치기"
            onClick={() => setMaterialsCollapsed(false)}
          >
            <ChevronRightIcon width={15} height={15} />
          </Button>
        )}
      </div>

      {detailOpen && agenda.item && (
        <RecordDrawer item={agenda.item} onClose={() => setDetailOpen(false)} />
      )}
    </section>
  )
}
