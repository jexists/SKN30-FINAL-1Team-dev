// 공지·지시사항 한 건의 상세. 팀장이 보는 쪽입니다.
//
// 목록은 제목을 한 줄로 자르고 본문은 아예 싣지 않습니다. 끝까지 읽을 자리가 따로 필요해
// 상세는 전부 오른쪽 드로어로 연다는 약속(components/Drawer)을 여기서도 따릅니다.
//
// 본문은 목록 응답에 없어 열 때 단건으로 받아 옵니다. 첫 응답에 본문까지 실으면 열지도
// 않을 글의 전문과 그 안의 사진 주소를 매번 나르게 됩니다.
//
// 지시사항이면 누가 했고 누가 못 했는지도 여기서 봅니다. 수신자와 그 상태는 목록 응답이
// 이미 싣고 오므로 따로 묻지 않습니다. 팀장이 팀원 대신 이행 처리하지는 않습니다. 그래야
// 이행 기록이 실제로 그 사람의 말이 됩니다.
import { useEffect, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import { EditIcon, EyeIcon, EyeOffIcon, MoreIcon, TrashIcon } from '@/components/icons'
import Popover from '@/components/Popover'
import Skeleton from '@/components/Skeleton'
import StatusBadge from '@/components/StatusBadge'
import { progressLabel, rollupLabel, statusLabel } from '@/shared/noticeStatus'
import type { NoticeManageListResponse, NoticeManageResponse } from '@/types'

import { periodLabel, stateOf, targetsLabel } from '../../noticeCatalog'

import styles from './NoticeDrawer.module.scss'

interface Props {
  row: NoticeManageListResponse
  /** 수정·숨김 전환·삭제가 처리되는 동안입니다. 메뉴를 잠급니다. */
  busy: boolean
  /** 본문 한 건을 받아 옵니다. 페이지가 쓰는 useNotices.loadNotice 를 그대로 받습니다. */
  loadNotice: (id: string) => Promise<NoticeManageResponse>
  onEdit: () => void
  onToggleHidden: () => void
  onDelete: () => void
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

export default function NoticeDrawer({
  row,
  busy,
  loadNotice,
  onEdit,
  onToggleHidden,
  onDelete,
  onClose,
}: Props) {
  const [body, setBody] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  const isDirective = row.type === 'DIRECTIVE'
  const state = stateOf(row)
  const rollup = rollupLabel(row.targets)

  useEffect(() => {
    let alive = true
    setError(null)

    void loadNotice(row.id)
      .then((notice) => {
        if (alive) setBody(notice.body)
      })
      .catch((caught: unknown) => {
        if (alive) setError(errorMessage(caught, '본문을 불러오지 못했습니다.'))
      })

    return () => {
      alive = false
    }
  }, [row.id, loadNotice, reloadKey])

  return (
    <Drawer
      title={row.title}
      sub={
        <span className={styles.when}>
          {row.author_display_name} · {periodLabel(row)}
        </span>
      }
      meta={
        <>
          <StatusBadge label={state.label} tone={state.tone} />
          {row.tag !== null && <i className={styles.badge}>{row.tag}</i>}
          {isDirective && <StatusBadge label={rollup.label} tone={rollup.tone} />}
        </>
      }
      actions={
        <Popover
          open={menuOpen}
          onClose={() => setMenuOpen(false)}
          align="end"
          compact
          label="공지 메뉴"
          trigger={
            <button
              type="button"
              className={styles.menuBtn}
              aria-label="공지 메뉴"
              aria-expanded={menuOpen}
              disabled={busy}
              onClick={() => setMenuOpen((value) => !value)}
            >
              <MoreIcon width={18} height={18} />
            </button>
          }
        >
          <div className={styles.menu}>
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false)
                onEdit()
              }}
            >
              <EditIcon width={15} height={15} />
              수정
            </button>
            <button
              type="button"
              aria-pressed={row.is_hidden}
              onClick={() => {
                setMenuOpen(false)
                onToggleHidden()
              }}
            >
              {row.is_hidden ? (
                <EyeIcon width={15} height={15} />
              ) : (
                <EyeOffIcon width={15} height={15} />
              )}
              {row.is_hidden ? '보이기' : '숨기기'}
            </button>
            <button
              type="button"
              className={styles.danger}
              onClick={() => {
                setMenuOpen(false)
                onDelete()
              }}
            >
              <TrashIcon width={15} height={15} />
              삭제
            </button>
          </div>
        </Popover>
      }
      onClose={onClose}
    >
      {/* 머리 정보. 목록에서 이미 들고 온 값이라 기다리지 않고 바로 섭니다. */}
      <dl className={styles.facts}>
        <div>
          <dt>수신자</dt>
          <dd>{targetsLabel(row)}</dd>
        </div>
        <div>
          <dt>노출 순서</dt>
          <dd className="tnum">{row.sort_order}</dd>
        </div>
        {isDirective && (
          <div>
            <dt>마감</dt>
            <dd className="tnum">{row.due_text ?? stamp(row.due_at)}</dd>
          </div>
        )}
        <div>
          <dt>최근 수정</dt>
          <dd className="tnum">{stamp(row.updated_at)}</dd>
        </div>
      </dl>

      <section className={styles.section}>
        <h3 className={styles.heading}>본문</h3>

        {error !== null ? (
          <p className={styles.detail} role="alert">
            {error}{' '}
            <Button variant="outline" size="sm" onClick={() => setReloadKey((key) => key + 1)}>
              다시 시도
            </Button>
          </p>
        ) : body === null ? (
          /* 본문은 글줄입니다. 한 덩어리로 덮으면 무엇이 오는지 읽히지 않아
             실제 문단과 같은 줄 간격으로 줄을 세웁니다. 문단 끝줄은 짧게 둡니다. */
          <div className={styles.pending} role="status">
            <span className="sr-only">본문을 불러오는 중입니다.</span>
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
             허용목록을 넓힐 일이 생기면 반드시 서버 쪽을 먼저 봅니다. */
          // oxlint-disable-next-line react/no-danger
          <div className={styles.detail} dangerouslySetInnerHTML={{ __html: body }} />
        )}
      </section>

      {/* 지시사항에만 섭니다. 공지는 수신자가 팀 전체라 이행이라는 것이 없습니다. */}
      {isDirective && (
        <section className={styles.section}>
          <h3 className={styles.heading}>
            이행 현황
            <span className={styles.summary}>{progressLabel(row.targets)}</span>
          </h3>

          {row.targets.length === 0 ? (
            <p className={styles.empty}>수신자가 없습니다.</p>
          ) : (
            <ul className={styles.targets}>
              {row.targets.map((target) => {
                const badge = statusLabel(target.status_code)
                return (
                  <li key={target.id}>
                    <div className={styles.targetHead}>
                      <strong className={styles.name}>{target.display_name}</strong>
                      <StatusBadge label={badge.label} tone={badge.tone} />
                      <span className={`${styles.changed} tnum`}>
                        {stamp(target.status_changed_at)}
                      </span>
                    </div>
                    {/* 미이행일 때만 옵니다. 이행으로 돌리면 서버가 지웁니다. */}
                    {target.status_reason !== null && target.status_reason !== '' && (
                      <p className={styles.reason}>{target.status_reason}</p>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      )}
    </Drawer>
  )
}
