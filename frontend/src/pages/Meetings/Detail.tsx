// 제출한 미팅 기록을 읽는 화면입니다. 작성 화면과 같은 컴포넌트를 읽기 모드로 씁니다.
import { useEffect, useId, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { errorMessage } from '@/api/errorMessage'
import { deleteReport } from '@/api/reportAgent'
import { useCurrentUser } from '@/auth/sessionContext'
import AttachmentPanel from '@/components/AttachmentPanel'
import Button, { buttonClass } from '@/components/Button'
import ColumnHead from '@/components/ColumnHead'
import {
  CalendarIcon,
  CheckIcon,
  ChevronDownIcon,
  // ChevronLeftIcon, // 접기 손잡이와 함께 내려둠
  ChevronRightIcon,
  DownloadIcon,
  EditIcon,
  SheetIcon,
  TeamIcon,
  TrashIcon,
} from '@/components/icons'
import Modal from '@/components/Modal'
import ReportView from '@/components/ReportView'
import { SkeletonDetail } from '@/components/Skeleton'
import StatusBadge, { type StatusTone } from '@/components/StatusBadge'
import { meetingComposePath, ROUTES } from '@/constants/routes'
import useCompanyDeals from '@/hooks/useCompanyDeals'
import RecordDrawer from '@/pages/Dashboard/components/RecordDrawer'
import SalesDealDrawer from '@/pages/Deals/SalesDealDrawer'
import DailyListLink from '@/pages/Daily/components/DailyListLink'
import { dailyListPath } from '@/pages/Daily/periods'
import { useAgendaItem } from '@/shared/agenda'
import { useReportDetail } from '@/shared/reportQuery'
import { isApprovedReportStatus, isAuthorEditableReportStatus } from '@/shared/reports'
import { showToast } from '@/shared/toast'
import { fmtDay, fmtDot, parseISO } from '@/utils/date'
import { meetingAttachmentPurposeOf } from '@/utils/attachment'
import type { MeetingDealSection, ReportAttachment } from '@/types'

import DealCardHeader from './components/DealCardHeader'
import DealPicker from './components/DealPicker'
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
          <ReportView className={styles.reportBody} body={section.values.body} />
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
  const navigate = useNavigate()
  // 삭제는 되돌릴 수 없으므로 한 번 물어봅니다.
  const [confirmingRemove, setConfirmingRemove] = useState(false)
  const [removing, setRemoving] = useState(false)
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
  // 자세히 보기는 작성 화면과 같은 드로어입니다. 일정 원본은 보고서에 없어 따로 받아 옵니다.
  // 읽기만 하므로 남의 일정도 받습니다. 팀장이 팀원 보고서의 근거 일정을 못 보면
  // 검토를 할 수가 없습니다. 쓰기는 작성 화면의 canWrite 가 따로 막습니다.
  const [detailOpen, setDetailOpen] = useState(false)
  const agenda = useAgendaItem(report?.agendaId ?? '', { ownOnly: false })
  // 관련 딜은 읽기만 합니다. 줄을 누르면 영업 화면과 같은 드로어로 그 자리에서 봅니다.
  const deals = useCompanyDeals(agenda.item?.customerCompanyId)
  const [openDealId, setOpenDealId] = useState<string | null>(null)

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
  const approved = isApprovedReportStatus(report.apiStatus)
  const meetingDay = parseISO(report.date)
  // 이 보고서가 다룬 딜만 세웁니다. 회사의 다른 딜은 이 기록과 상관이 없습니다.
  const dealIds = report.dealSections.map((section) => section.salesDealId)
  const reportDeals = deals.deals.filter((deal) => dealIds.includes(deal.id))

  // 원문과 참고자료는 같은 모양의 한 칸입니다 — 원문은 줄 목록, 참고자료는 사진 갤러리.
  const attachmentsOf = (purpose: 'meeting_source' | 'reference') =>
    report.attachments.filter((attachment) => meetingAttachmentPurposeOf(attachment) === purpose)

  const sourceAttachments = attachmentsOf('meeting_source')
  const referenceAttachments = attachmentsOf('reference')

  const attachmentPart = (
    label: string,
    purpose: 'meeting_source' | 'reference',
    attachments: ReportAttachment[],
  ) => {
    return (
      <div className={styles.part}>
        <h2 className={styles.sectionHead}>
          {label}
          {attachments.length > 0 && <span className={styles.count}>{attachments.length}건</span>}
        </h2>
        <AttachmentPanel
          attachments={attachments}
          reportId={report.id}
          readOnly
          gallery={purpose === 'reference'}
        />
      </div>
    )
  }

  const removeReport = async () => {
    setRemoving(true)
    try {
      await deleteReport(report.id)
      showToast('보고서를 삭제했습니다.')
      setConfirmingRemove(false)
      navigate(dailyListPath('meeting'))
    } catch (caught) {
      showToast(errorMessage(caught, '보고서를 삭제하지 못했습니다.'), { tone: 'error' })
    } finally {
      setRemoving(false)
    }
  }

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

        {/*
          잠그는 것은 서버입니다(approved 는 더 이상 고칠 수도 지울 수도 없습니다).
          잠긴 보고서에서도 버튼은 자리를 지키고, 누르면 왜 안 되는지를 말해 줍니다.
        */}
        <div className={styles.actions}>
          {isMine &&
            (editable ? (
              <Link
                className={buttonClass({ variant: 'outline' })}
                to={meetingComposePath(report.agendaId)}
              >
                <EditIcon width={15} height={15} />
                수정하기
              </Link>
            ) : (
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  showToast(
                    approved
                      ? '확정된 보고서라 수정할 수 없습니다.'
                      : '작성이 완료되어 수정할 수 없습니다.',
                    { tone: 'error' },
                  )
                }
              >
                <EditIcon width={15} height={15} />
                수정하기
              </Button>
            ))}

          {isMine && (
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
          {/* 왼쪽 자료 열 머리와 같은 줄에 섭니다. 오른쪽 끝은 이 문서를 종이로 내보내는 자리입니다. */}
          <ColumnHead title="보고서">
            <Button type="button" variant="outline" size="sm" onClick={() => window.print()}>
              <DownloadIcon width={15} height={15} />
              PDF 다운로드
            </Button>
          </ColumnHead>

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
            materialsCollapsed
              ? `${styles.materialsColumn} ${styles.collapsed}`
              : styles.materialsColumn
          }
        >
          {/* 열 머리는 접어도 남습니다. 한 열로 접히는 폭에서는 여기가 여닫이입니다. */}
          <ColumnHead title="보고서 작성 자료">
            {/* 접기 손잡이는 작성 화면과 같이 잠시 내려둡니다.
            <Button
              type="button"
              variant="outline"
              size="sm"
              iconOnly
              ref={collapseRef}
              className={styles.collapseAction}
              aria-expanded
              aria-controls="detail-materials-body"
              aria-label="미팅 자료 접기"
              onClick={() => {
                toggledRef.current = true
                setMaterialsCollapsed(true)
              }}
            >
              <ChevronLeftIcon width={15} height={15} />
            </Button>
            */}
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
          </ColumnHead>

          <div id="detail-materials-body" className={styles.materialsBody}>
            {/* 작성 화면과 같이 맥락과 자료를 판 두 장으로 나눕니다. */}
            <section className={styles.panel}>
              <div className={styles.panelHead}>
                <h2>미팅 정보</h2>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className={styles.panelAction}
                  disabled={!agenda.item}
                  onClick={() => setDetailOpen(true)}
                >
                  자세히 보기
                </Button>
              </div>
              {/* 작성 화면의 미팅 정보 판과 같은 차례입니다 — 어느 회사의 언제 기록인지 먼저. */}
              <div className={styles.context}>
                <strong>{report.hospital || '회사 미지정'}</strong>
                <span>
                  {report.contact || '담당자 미지정'} · 미팅일 {fmtDot(meetingDay)} {report.time}
                </span>
              </div>
              <MeetingFacts dept={report.dept} contact={report.contact} place={report.place} />

              {/* 딜 없이 공통 기록만 남긴 미팅도 있습니다. 그때는 이 칸을 세우지 않습니다. */}
              {dealIds.length > 0 && (
                <>
                  <div className={`${styles.panelHead} ${styles.dealHead}`}>
                    <h2>관련 딜</h2>
                    <span className={styles.count}>{dealIds.length}건</span>
                  </div>
                  <DealPicker
                    deals={reportDeals}
                    loading={deals.loading}
                    error={deals.error}
                    onRetry={deals.reload}
                    selected={dealIds}
                    onOpen={(deal) => setOpenDealId(deal.id)}
                    disabled={false}
                  />
                </>
              )}
            </section>

            {/* 원문 판이 먼저입니다. 배경자료로만 쓴 참고자료는 따로 한 판입니다. */}
            {(sourceAttachments.length > 0 || report.directTranscript) && (
              <section className={styles.panel}>
                {sourceAttachments.length > 0 &&
                  attachmentPart('미팅 원문 파일', 'meeting_source', sourceAttachments)}

                {/* 저장 원문(transcript)은 직접 입력에 파일 원문까지 합산한 것이라, 여기 깔면
                    바로 위 첨부 목록의 추출 텍스트를 한 번 더 읽게 됩니다. 사람이 직접 친 것만 둡니다.
                    직접 입력뿐이면 이 글이 곧 미팅 원문이라 그렇게 부릅니다. */}
                {report.directTranscript && (
                  <div className={styles.part}>
                    <h2 className={styles.sectionHead}>
                      {sourceAttachments.length > 0 ? '직접 입력' : '미팅 원문'}
                    </h2>
                    <p className={styles.transcript}>{report.directTranscript}</p>
                  </div>
                )}
              </section>
            )}

            {referenceAttachments.length > 0 && (
              <section className={styles.panel}>
                {attachmentPart('참고자료', 'reference', referenceAttachments)}
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
            ref={expandRef}
            className={styles.materialsToggle}
            aria-expanded={false}
            aria-controls="detail-materials"
            aria-label="미팅 자료 펼치기"
            onClick={() => {
              toggledRef.current = true
              setMaterialsCollapsed(false)
            }}
          >
            <ChevronRightIcon width={15} height={15} />
          </Button>
        )}
      </div>

      {detailOpen && agenda.item && (
        <RecordDrawer item={agenda.item} onClose={() => setDetailOpen(false)} />
      )}

      {/* 영업 화면과 같은 드로어입니다. 고칠 손잡이를 주지 않아 읽기만 합니다. */}
      {openDealId && (
        <SalesDealDrawer
          deal={deals.deals.find((deal) => deal.id === openDealId) ?? null}
          loading={deals.loading}
          error={deals.error}
          onRetry={deals.reload}
          onClose={() => setOpenDealId(null)}
        />
      )}

      {confirmingRemove && (
        <Modal
          title="보고서를 삭제할까요?"
          description={`${report.hospital} 미팅 보고서가 목록에서 사라집니다.`}
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
