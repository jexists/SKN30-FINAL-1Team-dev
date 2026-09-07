import type { ReactNode } from 'react'

import { CheckIcon } from '@/components/icons'
import type { ReportActivity } from '@/types'

import styles from './ActivityList.module.scss'

interface Props {
  activities: ReportActivity[]
  /** 읽기 모드면 체크가 사라지고 포함된 항목만 보입니다. */
  readOnly?: boolean
  /**
   * 읽기 모드에서 포함 표시를 세울지. 골라서 담은 목록에서는 무엇이 담겼는지 말해 주지만,
   * 애초에 고를 것이 없는 목록(주간·월간)에서는 체크 모양이 고를 수 있다는 오해를 만듭니다.
   */
  showMark?: boolean
  disabled?: boolean
  /** 항목 오른쪽에 붙는 상태·바로가기. 원본 보고서가 있는 자료에서 씁니다. */
  renderAside?: (item: ReportActivity) => ReactNode
  /** 항목 아래 전체 너비로 펼치는 보충 내용. */
  renderDetails?: (item: ReportActivity) => ReactNode
  onToggle?: (id: string) => void
}

export default function ActivityList({
  activities,
  readOnly = false,
  showMark = true,
  disabled = false,
  renderAside,
  renderDetails,
  onToggle,
}: Props) {
  const rows = readOnly ? activities.filter((a) => a.included) : activities
  /** 첫 칸(체크·표시)이 아예 없는 줄인지. 있으면 22px 칸을 잡아 둡니다. */
  const bare = readOnly && !showMark

  return (
    <div>
      {rows.length === 0 ? (
        <p className={styles.empty}>
          {readOnly ? '보고서에 포함된 활동이 없습니다.' : '이 날짜에 기록된 일정이 없습니다.'}
        </p>
      ) : (
        <ul className={styles.list}>
          {rows.map((item) => {
            const details = renderDetails?.(item)
            return (
              <li
                key={item.id}
                className={`${styles.item} ${bare ? styles.bare : ''} ${
                  !readOnly && !item.included ? styles.isOff : ''
                }`}
              >
                {bare ? null : readOnly ? (
                  <span className={styles.mark} aria-hidden="true">
                    <CheckIcon />
                  </span>
                ) : (
                  <button
                    type="button"
                    className={styles.check}
                    disabled={disabled}
                    aria-pressed={item.included}
                    aria-label={`${item.title} 보고서에 포함`}
                    onClick={() => onToggle?.(item.id)}
                  >
                    <CheckIcon />
                  </button>
                )}

                <div className={styles.body}>
                  <strong className={styles.title}>{item.title}</strong>
                  <span className={styles.desc}>{item.desc}</span>
                </div>

                <span className={styles.source}>{item.source}</span>

                {renderAside && <span className={styles.aside}>{renderAside(item)}</span>}
                {details && <div className={styles.details}>{details}</div>}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
