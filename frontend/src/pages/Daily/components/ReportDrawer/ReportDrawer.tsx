// 달력에서 날짜를 눌렀을 때 오른쪽에서 들어오는 보고서 패널입니다.
// /daily 의 주간 달력과 /daily/history 의 월 달력이 같은 것을 씁니다.
import { useEffect, useId, useRef } from 'react'
import { Link } from 'react-router'

import { buttonClass } from '@/components/Button'
import OwnerName from '@/components/OwnerName'
import ReportBody from '@/components/ReportBody'
import { ChevronRightIcon, CloseIcon } from '@/components/icons'
import { dailyComposePath } from '@/constants/routes'
import { agendaFor } from '@/shared/agenda'
import { useShowOwner } from '@/shared/scope'
import type { ReportKind } from '@/types'
import { fmtDot, parseISO, TODAY_ISO } from '@/utils/date'

import ReportStatusBadge from '../ReportStatusBadge'
import type { ListRow } from '../../rows'

import styles from './ReportDrawer.module.scss'

interface Props {
  dateISO: string
  /**
   * 그날 쓴 보고서. 하루에 일일과 주간이 겹칠 수 있고 미팅도 함께 오므로 배열입니다.
   * 어느 종류인지는 rows.ts 가 이미 한 모양으로 정리해 넘깁니다.
   */
  rows: ListRow[]
  /** 지금 보고 있는 기간 탭의 종류. 빈 날짜의 작성 화면을 그 양식으로 열어야 합니다. */
  kind: ReportKind
  onClose: () => void
}

export default function ReportDrawer({ dateISO, rows, kind, onClose }: Props) {
  const bodyRef = useRef<HTMLDivElement>(null)
  const showOwner = useShowOwner()
  const titleId = useId()

  // Modal 과 같은 처리입니다. Escape 로 닫고 배경은 스크롤을 멈추며,
  // 닫으면 눌렀던 날짜 칸으로 포커스가 돌아갑니다.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)

    const previousOverflow = document.body.style.overflow
    const previouslyFocused = document.activeElement as HTMLElement | null
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
      previouslyFocused?.focus()
    }
  }, [onClose])

  useEffect(() => {
    bodyRef.current
      ?.querySelector<HTMLElement>('a, button, [tabindex]:not([tabindex="-1"])')
      ?.focus()
  }, [])

  const isFuture = dateISO > TODAY_ISO
  const schedule = agendaFor(dateISO).length

  return (
    <div className={styles.scrim} onPointerDown={onClose}>
      <aside
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onPointerDown={(event) => event.stopPropagation()}
      >
        <header className={styles.head}>
          <h2 id={titleId} className="tnum">
            {fmtDot(parseISO(dateISO))}
          </h2>
          <button type="button" className={styles.close} onClick={onClose} aria-label="닫기">
            <CloseIcon />
          </button>
        </header>

        <div className={styles.body} ref={bodyRef}>
          {rows.length === 0 ? (
            <div className={styles.empty}>
              <p className={styles.emptyTitle}>제출된 보고서가 없습니다.</p>
              <p className={styles.emptyDesc}>
                {isFuture
                  ? '아직 오지 않은 날짜입니다.'
                  : schedule > 0
                    ? `이 날 캘린더 일정 ${schedule}건이 남아 있습니다. 그대로 초안을 만들 수 있습니다.`
                    : '이 날은 캘린더 일정도 없습니다.'}
              </p>

              {!isFuture && (
                <Link
                  className={buttonClass({ variant: 'outline' }, styles.cta)}
                  to={dailyComposePath(dateISO, kind)}
                >
                  이 날짜로 {kind}보고서 작성하기
                  <ChevronRightIcon />
                </Link>
              )}
            </div>
          ) : (
            rows.map((row) => (
              <article key={row.id} className={styles.item}>
                <div className={styles.tags}>
                  <span className={styles.kind}>{row.kindLabel}</span>
                  <ReportStatusBadge status={row.status} />
                  <span className={styles.approver}>{row.aside}</span>
                  {showOwner && <OwnerName name={row.author} />}
                </div>

                <h3 className={styles.title}>{row.title}</h3>

                {row.body ? (
                  <ReportBody className={styles.reportBody} body={row.body} />
                ) : (
                  <p className={styles.bodyEmpty}>내용이 비어 있습니다.</p>
                )}

                <p className={styles.counts}>{row.meta}</p>

                <Link className={buttonClass({ variant: 'outline' }, styles.cta)} to={row.to}>
                  전체 보기
                  <ChevronRightIcon />
                </Link>
              </article>
            ))
          )}
        </div>
      </aside>
    </div>
  )
}
