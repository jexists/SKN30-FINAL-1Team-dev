import { useState } from 'react'

import Button from '@/components/Button'
import { InfoIcon } from '@/components/icons'
import Popover from '@/components/Popover'
import Skeleton from '@/components/Skeleton'
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
  onSelectDuration: (suggestionId: string, duration: 30 | 60 | 90) => void
  onReject: (id: string) => void
  onGrab: (pointer: ReactPointerEvent, suggestion: AiSuggestion) => void
  /** 저장된 추천을 읽어 오는 중. LLM을 기다리는 것이 아니라 조회 한 번입니다. */
  loading?: boolean
  generationMessage?: string | null
  error?: string | null
  /**
   * 조회에 실패했을 때 추천 목록만 다시 읽습니다.
   *
   * 페이지 새로고침이 아닙니다. 캘린더 일정과 추천은 서로 다른 조회라, 페이지의
   * 재시도는 추천을 다시 부르지 않습니다. 이것이 없으면 사용자는 캘린더를 나갔다
   * 들어와야 추천을 다시 볼 수 있습니다.
   */
  onRetry?: () => void
}

export default function SuggestionPanel({
  suggestions,
  previewId,
  onPreview,
  onAccept,
  onSelectDuration,
  onReject,
  onGrab,
  loading = false,
  generationMessage = null,
  error = null,
  onRetry,
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
              계약관리 AI가 후속 논의가 필요한 날짜 한 개를 추천합니다. 일정에 반영하기 전
              소요시간을 선택하세요.
            </p>
          </Popover>
        </div>
      </header>

      {generationMessage && (
        <p className={styles.generating} role="status">
          {generationMessage}
        </p>
      )}

      {/*
        조회 한 번이라 금방 끝납니다. 그래도 그 사이에 "추천할 일정이 없습니다"를 보여 주면
        없는 것과 아직 모르는 것이 같아 보이므로, 자리표시자로 덮어 둡니다.
      */}
      {loading ? (
        <div className={styles.list} role="status">
          <span className="sr-only">AI 추천을 불러오는 중입니다.</span>
          <Skeleton height={168} radius="var(--r-md)" />
          <Skeleton height={168} radius="var(--r-md)" />
        </div>
      ) : error ? (
        <div className={styles.empty} role="alert">
          <p>{error}</p>
          {/* 이 버튼은 추천 목록만 다시 읽습니다 — 페이지 새로고침이 아닙니다. */}
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry}>
              다시 시도
            </Button>
          )}
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
              onPointerDown={(pointer) => onGrab(pointer, s)}
              onMouseEnter={() => onPreview(s.id)}
              onMouseLeave={() => onPreview(null)}
              onFocus={() => onPreview(s.id)}
              onBlur={() => onPreview(null)}
            >
              <div className={styles.when}>
                <span className="tnum">{fmtDay(parseISO(s.date))}</span>
                {s.refreshReason && <i className={styles.refreshed}>재추천됨</i>}
              </div>

              <h3 className={styles.org}>
                {s.hospital}
                <span className={styles.who}>{s.contact}</span>
              </h3>
              <p className={styles.title}>{s.title}</p>
              <p className={styles.reason}>{s.proposalReason}</p>
              {s.refreshReason && (
                <p className={styles.refreshReason}>재추천 이유: {s.refreshReason}</p>
              )}

              <fieldset className={styles.durationField}>
                <legend>소요시간</legend>
                <div className={styles.options}>
                  {s.durationOptions.map((duration) => (
                    <button
                      key={duration}
                      type="button"
                      className={`${styles.option} ${
                        duration === s.selectedDurationMinutes ? styles.isChosen : ''
                      }`}
                      aria-pressed={duration === s.selectedDurationMinutes}
                      onClick={() => onSelectDuration(s.id, duration)}
                    >
                      <span className="tnum">{duration}분</span>
                    </button>
                  ))}
                </div>
              </fieldset>

              <div className={styles.basis}>
                <i className={styles.kind}>{KIND_LABEL[s.kind]}</i>
                {s.basis.map((b) => (
                  <i key={b} className={styles.tag}>
                    {b}
                  </i>
                ))}
              </div>

              <div className={styles.actions}>
                <Button variant="outline" onClick={() => onReject(s.id)}>
                  추천 거절
                </Button>
                <Button
                  className={styles.accept}
                  disabled={s.selectedDurationMinutes === null}
                  onClick={() => onAccept(s)}
                >
                  추천일에 넣기
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
