import Button from '@/components/Button'
import { CloseIcon } from '@/components/icons'
import { KIND_LABEL } from '@/shared/agenda'
import type { AiSuggestion } from '@/types'
import { fmtDay, parseISO } from '@/utils/date'

import type { PointerEvent as ReactPointerEvent } from 'react'

import styles from './SuggestionPanel.module.scss'

interface Props {
  suggestions: AiSuggestion[]
  /** 미리보기 중인 추천. 그 날짜 칸에 고스트 칩이 떠 있습니다. */
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
  return (
    <aside className={styles.panel} aria-label="AI 추천 일정">
      <header className={styles.head}>
        <h2>AI 추천 일정</h2>
        <p className={styles.sub}>
          후속 조치 기한과 계약 만료일을 보고 고른 일정입니다. 카드를 끌어 원하는 날짜에 놓거나,
          추천한 날짜에 그대로 넣으세요.
        </p>
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
                <span className={styles.who}>
                  {s.dept} · {s.contact}
                </span>
              </h3>
              <p className={styles.title}>{s.title}</p>
              <p className={styles.reason}>{s.reason}</p>

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
