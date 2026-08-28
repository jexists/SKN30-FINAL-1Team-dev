import { useState } from 'react'

import Button from '@/components/Button'
import { CloseIcon, InfoIcon } from '@/components/icons'
import Popover from '@/components/Popover'
import { KIND_LABEL } from '@/shared/agenda'
import type { AiSuggestion } from '@/types'
import { fmtDay, parseISO } from '@/utils/date'

import type { PointerEvent as ReactPointerEvent } from 'react'

import styles from './SuggestionPanel.module.scss'

interface Props {
  suggestions: AiSuggestion[]
  /** 미리보기 중인 추천. 그 카드에 강조 테두리가 뜹니다. */
  previewId: string | null
  onPreview: (id: string | null) => void
  onAccept: (suggestion: AiSuggestion) => void
  onDismiss: (id: string) => void
  onGrab: (pointer: ReactPointerEvent, suggestion: AiSuggestion) => void
}

export default function SuggestionPanel({
  suggestions,
  previewId,
  onPreview,
  onAccept,
  onDismiss,
  onGrab,
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
              후속 조치 기한과 계약 만료일을 보고 고른 딜입니다. 카드를 끌어 원하는 날짜에 놓거나,
              추천한 날짜에 그대로 넣으세요.
            </p>
          </Popover>
        </div>
      </header>

      {suggestions.length === 0 ? (
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
              onPointerDown={(pointer) => onGrab(pointer, s)}
              onMouseEnter={() => onPreview(s.id)}
              onMouseLeave={() => onPreview(null)}
              onFocus={() => onPreview(s.id)}
              onBlur={() => onPreview(null)}
            >
              <div className={styles.when}>
                <span className="tnum">{fmtDay(parseISO(s.date))}</span>
                <span className={`${styles.time} tnum`}>
                  {s.time} · {s.dur}
                </span>
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
              <p className={styles.reason}>{s.proposalReason}</p>

              <div className={styles.basis}>
                <i className={styles.kind}>{KIND_LABEL[s.kind]}</i>
                {s.basis.map((b) => (
                  <i key={b} className={styles.tag}>
                    {b}
                  </i>
                ))}
              </div>

              <Button className={styles.accept} onClick={() => onAccept(s)}>
                추천일에 넣기
              </Button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
