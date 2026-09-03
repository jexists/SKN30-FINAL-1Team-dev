// 공지·팀장 지시사항 한 건의 전문입니다.
//
// 목록은 카드 폭에 맞춰 한 줄로 자르므로, 끝까지 읽을 자리가 따로 필요합니다.
// 상세는 전부 오른쪽 드로어로 연다는 대시보드의 약속을 그대로 따릅니다.
//
// 티커에는 제목과 올린 시각만 있습니다. 본문은 여기서 받아 옵니다. 첫 응답에 본문까지
// 실으면 열지도 않을 글의 전문을 매번 나르게 됩니다.
//
// 지시사항이고 내가 받은 것이면 이행 여부도 여기서 남깁니다. 팀장이 그 결과를 보는 자리는
// 여기가 아니라 공지관리 화면(팀장 지시사항 탭)입니다.
import { useState } from 'react'

import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import Skeleton from '@/components/Skeleton'
import StatusBadge from '@/components/StatusBadge'
import { errorMessage } from '@/api/errorMessage'
import { postedFull } from '@/shared/notices'
import { setNoticeStatus, statusLabel } from '@/shared/noticeStatus'
import { showToast } from '@/shared/toast'
import type { Notice, NoticeStatusResponse } from '@/types'

import MissReasonModal from '../MissReasonModal'
import { useNoticeDetail } from '../../useDashboard'

import styles from './NoticeDrawer.module.scss'

interface Props {
  /** 어느 카드에서 왔는지. '공지' 또는 '팀장 지시사항' */
  label: string
  notice: Notice
  /** 이행 여부가 바뀌면 티커의 배지를 다시 받아 옵니다. */
  onStatusChange?: () => void
  onClose: () => void
}

/** 본문 자리표시자. 문단 하나가 배열 하나이고, 값은 글줄의 너비입니다. */
const BODY_LINES = [
  ['100%', '96%', '88%', '54%'],
  ['100%', '92%', '67%'],
]

/** 2026-08-31T09:30:00+09:00 → 2026.08.31 09:30 */
function stamp(value: string | null): string {
  if (value === null) return '—'
  return `${value.slice(0, 10).replaceAll('-', '.')} ${value.slice(11, 16)}`
}

export default function NoticeDrawer({ label, notice, onStatusChange, onClose }: Props) {
  const { body, loading, error, reload } = useNoticeDetail(notice.id ?? null)
  // 저장이 끝나면 서버가 준 새 상태를 그대로 씁니다. 목록을 다시 받기 전까지의 값입니다.
  const [saved, setSaved] = useState<NoticeStatusResponse | null>(null)
  const [missing, setMissing] = useState(false)
  const [busy, setBusy] = useState(false)

  const status = saved ?? notice.myStatus ?? null
  const badge = status === null ? null : statusLabel(status.status_code)

  const decide = async (statusCode: 'done' | 'not_done', reason: string | null) => {
    if (notice.id === undefined) return
    setBusy(true)
    try {
      const updated = await setNoticeStatus(notice.id, statusCode, reason)
      setSaved(updated.my_status)
      setMissing(false)
      showToast(statusCode === 'done' ? '이행으로 표시했습니다.' : '미이행으로 표시했습니다.')
      onStatusChange?.()
    } catch (caught: unknown) {
      showToast(errorMessage(caught, '상태를 바꾸지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Drawer
        title={label}
        sub={<span className={styles.when}>{postedFull(notice)}</span>}
        meta={badge === null ? undefined : <StatusBadge label={badge.label} tone={badge.tone} />}
        footer={
          // 내가 받은 지시일 때만 섭니다. 공지이거나 남에게 간 지시면 누를 것이 없습니다.
          status === null ? undefined : (
            <>
              <Button
                variant="outline"
                disabled={busy}
                aria-pressed={status.status_code === 'not_done'}
                onClick={() => setMissing(true)}
              >
                미이행
              </Button>
              <Button
                disabled={busy || status.status_code === 'done'}
                aria-pressed={status.status_code === 'done'}
                onClick={() => void decide('done', null)}
              >
                이행
              </Button>
            </>
          )
        }
        onClose={onClose}
      >
        {/* 머리말은 목록에서 이미 들고 온 값이라 기다리지 않고 바로 섭니다.
            본문 자리만 비워 두어야 누른 것이 열렸다는 것이 보입니다. */}
        <h3 className={styles.headline}>{notice.text}</h3>

        {/* 팀장이 남에게 간 지시를 열었을 때만 섭니다. 여기는 자리가 넉넉해 이름을 다 적습니다. */}
        {notice.recipients && (
          <p className={styles.recipients}>받는 사람 {notice.recipients.join(', ')}</p>
        )}

        {/* 지시사항의 머리 정보. 언제까지 무엇을 누가 해야 하는지 한자리에 둡니다. */}
        {status !== null && (
          <dl className={styles.facts}>
            <div>
              <dt>지시자</dt>
              <dd>{notice.author}</dd>
            </div>
            <div>
              <dt>지시일</dt>
              <dd className="tnum">{postedFull(notice)}</dd>
            </div>
            <div>
              <dt>마감일</dt>
              <dd className="tnum">{notice.due ?? '—'}</dd>
            </div>
            <div>
              <dt>우선순위</dt>
              <dd>{notice.tag}</dd>
            </div>
            <div>
              <dt>현재 상태</dt>
              <dd>{badge?.label}</dd>
            </div>
            <div>
              <dt>{status.status_code === 'done' ? '완료일' : '변경일'}</dt>
              <dd className="tnum">{stamp(status.status_changed_at)}</dd>
            </div>
          </dl>
        )}

        {/* 지난 미이행 사유. 이행으로 돌리면 서버가 지웁니다. */}
        {status?.status_reason != null && status.status_reason !== '' && (
          <p className={styles.reason}>미이행 사유 · {status.status_reason}</p>
        )}

        {error ? (
          <p className={styles.detail} role="alert">
            {error}{' '}
            <Button variant="outline" size="sm" onClick={reload}>
              다시 시도
            </Button>
          </p>
        ) : loading || body === null ? (
          /* 본문은 글줄입니다. 한 덩어리로 덮으면 무엇이 오는지 읽히지 않아
             실제 문단과 같은 줄 간격으로 줄을 세웁니다. 문단 끝줄은 짧게 둡니다. */
          <div className={styles.pending} role="status">
            <span className="sr-only">전문을 불러오는 중입니다.</span>
            {BODY_LINES.map((paragraph, at) => (
              <p key={at} className={styles.pendingParagraph}>
                {paragraph.map((width, line) => (
                  <Skeleton key={line} width={width} height={11} />
                ))}
              </p>
            ))}
          </div>
        ) : (
          /* 본문은 팀장이 편집기로 쓴 HTML 입니다. 서버(app/services/html_sanitize.py)가
             저장할 때 허용 태그만 남기므로 여기서 다시 자르지 않고 그대로 그립니다.
             허용목록을 넓힐 일이 생기면 반드시 서버 쪽을 먼저 봅니다.
             사진도 본문 안에 있습니다. 주소는 서버가 응답할 때마다 새로 발급합니다. */
          // oxlint-disable-next-line react/no-danger
          <div className={styles.detail} dangerouslySetInnerHTML={{ __html: body.body }} />
        )}
      </Drawer>

      {missing && (
        <MissReasonModal
          busy={busy}
          onCancel={() => setMissing(false)}
          onSubmit={(reason) => void decide('not_done', reason)}
        />
      )}
    </>
  )
}
