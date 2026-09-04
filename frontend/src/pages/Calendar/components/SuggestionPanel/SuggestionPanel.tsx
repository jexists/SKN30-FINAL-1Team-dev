import { useState } from 'react'

import Button from '@/components/Button'
import { CloseIcon, InfoIcon } from '@/components/icons'
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
  /** 카드에서 다른 시간 후보를 고릅니다. */
  onSelectOption: (suggestionId: string, candidateId: string) => void
  onDismiss: (id: string) => void
  onGrab: (pointer: ReactPointerEvent, suggestion: AiSuggestion) => void
  /** 저장된 추천을 읽어 오는 중. LLM을 기다리는 것이 아니라 조회 한 번입니다. */
  loading?: boolean
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
  onSelectOption,
  onDismiss,
  onGrab,
  loading = false,
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
              후속 조치 기한과 계약 만료일을 보고 고른 딜입니다. 보고서를 확정하거나 딜을 옮기면
              그때 다시 계산합니다. 카드를 끌어 원하는 날짜에 놓거나, 추천한 날짜에 그대로 넣으세요.
            </p>
          </Popover>
        </div>
      </header>

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

              {/*
                일정관리 에이전트가 겹치지 않는 시간을 여러 개 내놓습니다. 가장 추천하는
                것을 위에 크게 두고, 나머지는 눌러서 바꿀 수 있게 칩으로 둡니다.
              */}
              {s.options.length > 1 && (
                <div className={styles.options}>
                  {s.options.map((option) => (
                    <button
                      key={option.candidateId}
                      type="button"
                      className={`${styles.option} ${
                        option.candidateId === s.selectedCandidateId ? styles.isChosen : ''
                      }`}
                      aria-pressed={option.candidateId === s.selectedCandidateId}
                      onClick={() => onSelectOption(s.id, option.candidateId)}
                    >
                      <span className="tnum">
                        {fmtDay(parseISO(option.date))} {option.time}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {s.scheduledVisitNote && (
                <p className={styles.scheduledVisit}>{s.scheduledVisitNote}</p>
              )}

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
