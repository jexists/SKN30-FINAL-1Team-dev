import { useState } from 'react'

import Button from '@/components/Button'
import { CloseIcon, InfoIcon, RefreshIcon } from '@/components/icons'
import Popover from '@/components/Popover'
import { KIND_LABEL } from '@/shared/agenda'
import type { AiSuggestion, AiSuggestionReady } from '@/types'
import { fmtDay, parseISO } from '@/utils/date'

import type { PointerEvent as ReactPointerEvent } from 'react'

import styles from './SuggestionPanel.module.scss'

interface Props {
  suggestions: AiSuggestion[]
  /** 미리보기 중인 추천. 그 카드에 강조 테두리가 뜹니다. */
  previewId: string | null
  onPreview: (id: string | null) => void
  /** 접힌 카드를 펼쳐 실제 날짜/시간을 계산합니다(1차 제안 + 일정 후보 호출). */
  onExpand: (id: string) => void
  onAccept: (suggestion: AiSuggestionReady) => void
  onDismiss: (id: string) => void
  onGrab: (pointer: ReactPointerEvent, suggestion: AiSuggestionReady) => void
  /** 추천을 다시 받아 옵니다. */
  onRefresh: () => void
  /** 다시 받아 오는 중. 아이콘이 돌고 버튼은 잠깁니다. */
  refreshing?: boolean
}

export default function SuggestionPanel({
  suggestions,
  previewId,
  onPreview,
  onExpand,
  onAccept,
  onDismiss,
  onGrab,
  onRefresh,
  refreshing = false,
}: Props) {
  // 무엇을 보고 고른 추천인지는 한 번 읽으면 그만입니다. 카드보다 먼저 자리를
  // 차지하지 않도록 물음표 하나로 접어 두고 눌렀을 때만 폅니다.
  const [helpOpen, setHelpOpen] = useState(false)

  return (
    <aside className={styles.panel} aria-label="AI 추천 일정">
      <header className={styles.head}>
        <h2>AI 추천 일정</h2>

        <div
          className={styles.help}
          onMouseEnter={() => setHelpOpen(true)}
          onMouseLeave={() => setHelpOpen(false)}
        >
          <Popover
            open={helpOpen}
            onClose={() => setHelpOpen(false)}
            label="AI 추천 기준"
            trigger={
              <button
                type="button"
                className={styles.helpBtn}
                aria-label="AI 추천 기준 설명"
                aria-expanded={helpOpen}
                onClick={() => setHelpOpen((v) => !v)}
                onFocus={() => setHelpOpen(true)}
                onBlur={() => setHelpOpen(false)}
              >
                <InfoIcon width={15} height={15} />
              </button>
            }
          >
            <p className={styles.sub}>
              후속 조치 기한과 계약 만료일을 보고 고른 딜입니다. "일정 확인"을 누르면 실제
              날짜·시간을 계산합니다. 카드를 끌어 원하는 날짜에 놓거나, 추천한 날짜에 그대로
              넣으세요.
            </p>
          </Popover>
        </div>

        <button
          type="button"
          className={`${styles.refresh} ${refreshing ? styles.isSpinning : ''}`}
          onClick={onRefresh}
          disabled={refreshing}
          aria-label="AI 추천 새로고침"
        >
          <RefreshIcon width={15} height={15} />
          새로고침
        </button>
      </header>

      {refreshing ? (
        <div className={styles.empty}>
          <p>추천을 새로 받는 중입니다.</p>
        </div>
      ) : suggestions.length === 0 ? (
        <div className={styles.empty}>
          <p>지금은 추천할 일정이 없습니다.</p>
          <p className={styles.emptyHint}>고객 활동이 쌓이면 다시 제안합니다.</p>
        </div>
      ) : (
        <ul className={styles.list}>
          {suggestions.map((s) => (
            <li
              key={s.id}
              className={`${styles.card} ${previewId === s.id ? styles.isPreview : ''}`}
              onPointerDown={(pointer) => {
                if (s.status === 'ready') onGrab(pointer, s)
              }}
              onMouseEnter={() => onPreview(s.id)}
              onMouseLeave={() => onPreview(null)}
              onFocus={() => onPreview(s.id)}
              onBlur={() => onPreview(null)}
            >
              <div className={styles.when}>
                {s.status === 'ready' ? (
                  <>
                    <span className="tnum">{fmtDay(parseISO(s.date))}</span>
                    <span className={`${styles.time} tnum`}>
                      {s.time} · {s.dur}
                    </span>
                  </>
                ) : (
                  <span className="tnum">우선순위 {s.priority}</span>
                )}
                <button
                  type="button"
                  className={styles.dismiss}
                  aria-label={`${s.hospital} ${s.title} 추천 닫기`}
                  onClick={() => onDismiss(s.id)}
                >
                  <CloseIcon width={14} height={14} />
                </button>
              </div>

              <h3 className={styles.org}>
                {s.hospital}
                <span className={styles.who}>{s.contact}</span>
              </h3>
              <p className={styles.title}>{s.title}</p>
              <p className={styles.reason}>{s.status === 'ready' ? s.proposalReason : s.reason}</p>
              {s.status === 'error' && <p className={styles.reason}>{s.error}</p>}

              {s.status === 'ready' && (
                <div className={styles.basis}>
                  <i className={styles.kind}>{KIND_LABEL[s.kind]}</i>
                  {s.basis.map((b) => (
                    <i key={b} className={styles.tag}>
                      {b}
                    </i>
                  ))}
                </div>
              )}

              {s.status === 'ready' ? (
                <Button className={styles.accept} onClick={() => onAccept(s)}>
                  추천일에 넣기
                </Button>
              ) : (
                <Button
                  className={styles.accept}
                  onClick={() => onExpand(s.id)}
                  disabled={s.status === 'loading'}
                >
                  {s.status === 'loading'
                    ? '일정 확인 중…'
                    : s.status === 'error'
                      ? '다시 시도'
                      : '일정 확인'}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
