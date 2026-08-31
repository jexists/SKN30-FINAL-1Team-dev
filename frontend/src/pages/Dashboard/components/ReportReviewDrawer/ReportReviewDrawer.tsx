// 팀장이 일정에 붙은 보고서를 열어 확정하거나 반려하는 자리.
//
// 본문 항목을 여기서 다시 나열하지 않습니다. 미팅 목적·주요 논의사항·고객 요구사항 같은
// 것은 작성 화면이 쓴 양식(template_snapshot) 안에 이미 있고, ReportFields 가 그 양식대로
// 그려 줍니다. 여기서 항목을 따로 적어 두면 양식이 바뀔 때마다 두 곳을 같이 고쳐야 합니다.
//
// 팀원에게는 이 드로어를 열지 않습니다. 자기 보고서는 업무보고서 상세로 갑니다.
import { useState } from 'react'
import { Link } from 'react-router'

import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import ReportFields from '@/components/ReportFields'
import StatusBadge from '@/components/StatusBadge'
import { InlineLoader } from '@/components/Skeleton'
import { useCurrentUser } from '@/auth/sessionContext'
import { meetingReportPath } from '@/constants/routes'
import { toMeetingReport } from '@/pages/Meetings/useMeetingReports'
import { useReportDetail } from '@/shared/reportQuery'
import { isReviewable, reviewLabel, reviewReport } from '@/shared/reviewDecision'
import { showToast } from '@/shared/toast'
import { errorMessage } from '@/api/errorMessage'

import RejectReasonModal from '../RejectReasonModal'

import styles from './ReportReviewDrawer.module.scss'

interface Props {
  reportId: string
  /** 확정·반려가 끝나면 목록의 배지를 다시 받아 옵니다. */
  onReviewed: () => void
  onClose: () => void
}

/** 2026-08-31T09:30:00+09:00 → 2026.08.31 09:30 */
function stamp(value: string | null): string {
  if (value === null) return '—'
  return `${value.slice(0, 10).replaceAll('-', '.')} ${value.slice(11, 16)}`
}

export default function ReportReviewDrawer({ reportId, onReviewed, onClose }: Props) {
  const { memberId } = useCurrentUser()
  const { item, loading, error } = useReportDetail(reportId, '보고서를 불러오지 못했습니다.')
  const [rejecting, setRejecting] = useState(false)
  const [busy, setBusy] = useState(false)

  const report = item === null ? null : toMeetingReport(item)
  const status = item?.status_code ?? 'draft'
  const badge = reviewLabel(status)

  // 자기가 쓴 보고서는 자기가 확정하지 않습니다. 서버도 같은 조건으로 거절합니다.
  const canReview = item !== null && isReviewable(status) && item.author_member_id !== memberId

  const decide = async (decision: 'approve' | 'reject', reason: string | null) => {
    setBusy(true)
    try {
      await reviewReport(reportId, decision, reason)
      showToast(decision === 'approve' ? '보고서를 확정했습니다.' : '보고서를 반려했습니다.')
      setRejecting(false)
      onReviewed()
      onClose()
    } catch (caught: unknown) {
      showToast(errorMessage(caught, '상태를 바꾸지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Drawer
        wide
        title={report?.hospital || report?.title || '보고서'}
        sub={report === null ? undefined : [report.date, report.time].filter(Boolean).join(' ')}
        meta={<StatusBadge label={badge.label} tone={badge.tone} />}
        footer={
          canReview ? (
            <>
              <Button variant="outline" disabled={busy} onClick={() => setRejecting(true)}>
                반려
              </Button>
              <Button disabled={busy} onClick={() => void decide('approve', null)}>
                확정
              </Button>
            </>
          ) : (
            <Button variant="outline" onClick={onClose}>
              닫기
            </Button>
          )
        }
        onClose={onClose}
      >
        {loading && <InlineLoader label="보고서를 불러오는 중입니다." />}
        {error !== null && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}

        {item !== null && report !== null && (
          <>
            <dl className={styles.facts}>
              <div>
                <dt>거래처</dt>
                <dd>{report.hospital || '—'}</dd>
              </div>
              <div>
                <dt>미팅 일시</dt>
                <dd className="tnum">{[report.date, report.time].filter(Boolean).join(' ')}</dd>
              </div>
              <div>
                <dt>담당 팀원</dt>
                <dd>{report.owner}</dd>
              </div>
              <div>
                <dt>담당자</dt>
                <dd>{[report.dept, report.contact].filter(Boolean).join(' · ') || '—'}</dd>
              </div>
              {report.salesDeal !== undefined && (
                <div>
                  <dt>관련 영업</dt>
                  <dd>{report.salesDeal.label}</dd>
                </div>
              )}
            </dl>

            {/* 지난 반려 사유. 다시 낸 보고서를 볼 때 무엇을 지적했는지 함께 봐야 합니다.
                작성자가 적은 note 와는 다른 칸이라 여기에 남의 메모가 섞이지 않습니다. */}
            {item.review_note !== null && item.review_note !== '' && (
              <section className={styles.section}>
                <h3 className={styles.heading}>지난 반려 사유</h3>
                <p className={styles.reason}>{item.review_note}</p>
              </section>
            )}

            <section className={styles.section}>
              <h3 className={styles.heading}>보고 내용</h3>
              <ReportFields template={report.template} values={report.values} readOnly />
            </section>

            {(report.aiEvidence !== undefined || report.aiGeneratedAt !== undefined) && (
              <section className={styles.section}>
                <h3 className={styles.heading}>🤖 AI 분석 결과</h3>
                {report.aiEvidence !== undefined && (
                  <p className={styles.evidence}>{report.aiEvidence}</p>
                )}
                {report.aiGeneratedAt !== undefined && (
                  <p className={styles.hint}>작성 도움 {stamp(report.aiGeneratedAt)}</p>
                )}
              </section>
            )}

            <section className={styles.section}>
              <dl className={styles.facts}>
                <div>
                  <dt>작성자</dt>
                  <dd>{item.author_display_name}</dd>
                </div>
                <div>
                  <dt>작성일</dt>
                  <dd className="tnum">{stamp(item.created_at)}</dd>
                </div>
                {item.reviewed_at !== null && (
                  <div>
                    <dt>검토일</dt>
                    <dd className="tnum">{stamp(item.reviewed_at)}</dd>
                  </div>
                )}
              </dl>
              <Link className={styles.link} to={meetingReportPath(item.id)}>
                업무보고서 전체 보기
              </Link>
            </section>

            {!canReview && isReviewable(status) && (
              <p className={styles.hint}>
                자기가 쓴 보고서는 스스로 확정할 수 없습니다.
              </p>
            )}
          </>
        )}
      </Drawer>

      {rejecting && (
        <RejectReasonModal
          busy={busy}
          onCancel={() => setRejecting(false)}
          onSubmit={(reason) => void decide('reject', reason)}
        />
      )}
    </>
  )
}
