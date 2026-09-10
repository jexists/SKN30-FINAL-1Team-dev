// 7칸짜리 날짜 줄. 대시보드 주간 일정과 업무 보고 제출 이력이 같은 모양을 씁니다.
//
// 범위를 스스로 정하지 않습니다. 대시보드는 오늘이 셋째 칸인 롤링 7일을,
// 업무 보고는 startOfWeek 로 잡은 일–토 한 주를 넘깁니다.
import type { KeyboardEvent, ReactNode } from 'react'

import { addDays, iso, parseISO, TODAY_ISO, WD } from '@/utils/date'

import styles from './WeekStrip.module.scss'

interface Props {
  days: Date[]
  /** 빈 문자열이면 선택 표시를 하지 않습니다. */
  selectedISO: string
  onSelect: (dateISO: string) => void
  /** 화살표 이동이 보이는 범위를 벗어날 때. 범위를 옮기는 건 호출부 몫입니다. */
  onOutOfRange?: (dateISO: string) => void
  /**
   * 날짜 아래 표시. 대시보드는 일정·납기 점, 업무 보고는 상태 점입니다.
   * 선택된 칸은 배경이 파랗게 차므로 isSelected 를 함께 넘겨 색을 뒤집게 합니다.
   * (표시의 스타일은 호출부 모듈에 있어 여기서 후손 선택자로 덮을 수 없습니다.)
   */
  renderMarks?: (dateISO: string, isSelected: boolean) => ReactNode
  label: string
  /** 선택 칸 아래 삼각형. 바로 아래로 내용이 이어지는 화면에서만 씁니다. */
  notch?: boolean
  /** 배경을 채우지 않고 테두리만 강조해야 하는 날짜 선택 화면에서 씁니다. */
  selectionStyle?: 'filled' | 'outline'
  /** 이 날짜 뒤는 고를 수 없습니다. 미래의 업무보고를 막는 화면에서 씁니다. */
  maxISO?: string
}

export default function WeekStrip({
  days,
  selectedISO,
  onSelect,
  onOutOfRange,
  renderMarks,
  label,
  notch = false,
  selectionStyle = 'filled',
  maxISO,
}: Props) {
  const keys = days.map(iso)

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()

    const step = event.key === 'ArrowRight' ? 1 : -1
    const from = selectedISO || keys[0]
    const next = iso(addDays(parseISO(from), step))

    if (maxISO && next > maxISO) return
    if (!keys.includes(next)) onOutOfRange?.(next)
    onSelect(next)

    // 렌더 후 새 셀로 포커스를 옮깁니다.
    requestAnimationFrame(() => {
      document.querySelector<HTMLButtonElement>(`[data-iso="${next}"]`)?.focus()
    })
  }

  return (
    <div
      className={`${styles.grid} ${notch ? styles.hasNotch : ''}`}
      role="tablist"
      aria-label={label}
      onKeyDown={onKeyDown}
    >
      {days.map((d, index) => {
        const key = keys[index]
        const dow = d.getDay()
        const isToday = key === TODAY_ISO
        const isSelected = key === selectedISO
        const isDisabled = maxISO !== undefined && key > maxISO

        const cls = [
          styles.day,
          isToday && styles.isToday,
          isSelected && (selectionStyle === 'outline' ? styles.isOutline : styles.isSelected),
          dow === 0 && styles.isSun,
          dow === 6 && styles.isSat,
        ]
          .filter(Boolean)
          .join(' ')

        return (
          <button
            key={key}
            type="button"
            role="tab"
            className={cls}
            data-iso={key}
            aria-selected={isSelected}
            disabled={isDisabled}
            // 선택이 없으면 첫 칸 하나만 탭 순서에 둡니다.
            tabIndex={(selectedISO ? isSelected : index === 0) ? 0 : -1}
            onClick={() => onSelect(key)}
          >
            <span className={styles.wd}>
              {WD[dow]}
              {isToday && <em className={styles.todayTag}> · 오늘</em>}
            </span>
            <span className={`${styles.num} tnum`}>{String(d.getDate()).padStart(2, '0')}</span>
            {d.getDate() === 1 && (
              <span className={`${styles.month} tnum`}>{d.getMonth() + 1}월</span>
            )}
            <span className={styles.marks}>{renderMarks?.(key, isSelected)}</span>
          </button>
        )
      })}
    </div>
  )
}
