// 공지·팀장 지시사항 한 건의 전문입니다. 여는 곳에 따라 껍데기만 둘입니다.
//
// - 카드의 줄을 누르면 단독 드로어(NoticeDrawer)로 엽니다. 카드에는 제목만 있어 본문을 받아 옵니다.
// - 목록 드로어의 줄을 누르면 목록 왼쪽 패널(NoticePanel)로 엽니다. 본문은 목록 응답에 이미 있습니다.
//
// 지시사항이고 내가 받은 것이면 이행 여부도 여기서 남깁니다. 팀장이 그 결과를 보는 자리는
// 여기가 아니라 공지관리 화면(팀장 지시사항 탭)입니다.
import { useState } from 'react'

import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import { CloseIcon } from '@/components/icons'
import ImageLightbox, { clickedImage } from '@/components/ImageLightbox'
import Skeleton from '@/components/Skeleton'
import StatusBadge from '@/components/StatusBadge'
import { errorMessage } from '@/api/errorMessage'
import { postedFull } from '@/shared/notices'
import { setNoticeStatus, statusLabel } from '@/shared/noticeStatus'
import { showToast } from '@/shared/toast'
import type { Notice, NoticeStatusResponse } from '@/types'

import MissReasonModal from '../MissReasonModal'
import { useNoticeDetail } from '../../useDashboard'

// 파일 이름이 NoticeDrawer 면 개발 서버에서 pages/Notices 의 NoticeDrawer 와 클래스 이름이
// 같아져(NoticeDrawer__facts) 서로 덮어씁니다. 그래서 이름을 달리 둡니다.
import styles from './NoticeDetail.module.scss'

interface Props {
  notice: Notice
  /** 이행 여부가 바뀌면 티커 배지와 목록을 다시 받아 옵니다. */
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

/** 이행 여부 한 벌. 본문의 배지와 아래 버튼이 같은 값을 봅니다. */
function useNoticeDecision(notice: Notice, onStatusChange?: () => void) {
  // 저장이 끝나면 서버가 준 새 상태를 그대로 씁니다. 목록을 다시 받기 전까지의 값입니다.
  const [saved, setSaved] = useState<NoticeStatusResponse | null>(null)
  const [missing, setMissing] = useState(false)
  const [busy, setBusy] = useState(false)

  const status = saved ?? notice.myStatus ?? null

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

  return { status, busy, missing, setMissing, decide }
}

type Decision = ReturnType<typeof useNoticeDecision>

function NoticeActions({ decision }: { decision: Decision }) {
  const { status, busy, missing, setMissing, decide } = decision
  // 내가 받은 지시일 때만 섭니다. 공지이거나 남에게 간 지시면 누를 것이 없습니다.
  if (status === null) return null
  return (
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

interface ContentProps {
  notice: Notice
  decision: Decision
  /** 본문 HTML. 아직 받는 중이면 null 입니다. */
  html: string | null
  error?: string | null
  onRetry?: () => void
}

function NoticeContent({ notice, decision, html, error, onRetry }: ContentProps) {
  const { status } = decision
  const badge = status === null ? null : statusLabel(status.status_code)
  // 본문 안의 사진을 눌렀을 때 크게 볼 것. 누르지 않았으면 null 입니다.
  const [zoom, setZoom] = useState<{ src: string; alt: string } | null>(null)

  return (
    <>
      {/* 왼쪽은 누구의 글인지(지시면 내 이행 상태), 오른쪽은 올린 일시입니다. */}
      <div className={styles.when}>
        {badge !== null ? (
          <StatusBadge label={badge.label} tone={badge.tone} />
        ) : (
          <span className={styles.author}>{notice.author}</span>
        )}
        <time className="tnum">{postedFull(notice)}</time>
      </div>

      {/* 지시사항의 머리 정보. 언제까지 무엇을 해야 하는지 본문보다 먼저 보여야 합니다. */}
      {status !== null && (
        <dl className={styles.facts}>
          <div>
            <dt>지시자</dt>
            <dd>{notice.author}</dd>
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
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry}>
              다시 시도
            </Button>
          )}
        </p>
      ) : html === null ? (
        /* 본문은 글줄입니다. 실제 문단과 같은 줄 간격으로 줄을 세워 도착해도 밀리지 않게 합니다. */
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
        <div
          className={styles.detail}
          dangerouslySetInnerHTML={{ __html: html }}
          onClick={(event) => {
            const image = clickedImage(event)
            if (image) setZoom(image)
          }}
        />
      )}

      {zoom && <ImageLightbox {...zoom} onClose={() => setZoom(null)} />}
    </>
  )
}

/** 카드의 줄을 눌렀을 때. 상세 하나만 드로어로 엽니다. */
export default function NoticeDrawer({ notice, onStatusChange, onClose }: Props) {
  const { body, loading, error, reload } = useNoticeDetail(notice.id ?? null)
  const decision = useNoticeDecision(notice, onStatusChange)

  return (
    <Drawer
      title={notice.text}
      footer={decision.status === null ? undefined : <NoticeActions decision={decision} />}
      onClose={onClose}
    >
      <NoticeContent
        notice={notice}
        decision={decision}
        html={loading || body === null ? null : body.body}
        error={error}
        onRetry={reload}
      />
    </Drawer>
  )
}

/** 목록 드로어의 줄을 눌렀을 때. 목록 왼쪽에 붙는 패널입니다. 머리 치수는 Drawer 와 같습니다. */
export function NoticePanel({ notice, onStatusChange, onClose }: Props) {
  const decision = useNoticeDecision(notice, onStatusChange)

  return (
    <section className={styles.panel} aria-label={`${notice.text} 상세`}>
      <header className={styles.panelHead}>
        <h2>{notice.text}</h2>
        <button type="button" className={styles.close} onClick={onClose} aria-label="상세 닫기">
          <CloseIcon />
        </button>
      </header>
      <div className={styles.panelBody}>
        <NoticeContent notice={notice} decision={decision} html={notice.detail} />
      </div>
      {decision.status !== null && (
        <footer className={styles.panelFoot}>
          <NoticeActions decision={decision} />
        </footer>
      )}
    </section>
  )
}
