// 여럿 중 하나를 고르는 한 줄. 단계·분류·상태·기간·보기 방식이 모두 이것을 씁니다.
//
// 높이와 모서리는 컴포넌트가 정합니다. 화면마다 padding 으로 높이를 만들면 글자 크기가
// 조금만 달라져도 옆의 검색창·버튼과 줄이 어긋납니다.
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import type { ColumnTone } from '@/types'

import styles from './Tabs.module.scss'

export interface TabItem<T extends string = string> {
  value: T
  label: string
  /** 옆에 붙는 건수. 없으면 숫자를 그리지 않습니다. */
  count?: number
  /** 앞에 붙는 색 점. '전체' 탭처럼 색이 없는 탭은 생략합니다. */
  tone?: ColumnTone
  /** 글자 앞 아이콘. */
  icon?: ReactNode
  /** 넘기면 버튼이 아니라 링크로 그립니다. 주소가 곧 상태인 자리에 씁니다. */
  to?: string
}

interface Props<T extends string> {
  items: TabItem<T>[]
  value: T
  /** 링크로 그리는 경우에는 필요 없습니다. */
  onChange?: (value: T) => void
  /** 묶음의 이름. 화면마다 '계약 단계'·'보기 방식' 처럼 다릅니다. */
  label: string
  /**
   * pill 은 알약이 각각 서고, segmented 는 한 통 안에 함께 담기며,
   * underline 은 밑줄만 그어 머리말 아래에서 화면을 가릅니다.
   */
  variant?: 'pill' | 'segmented' | 'underline'
  /** 툴바가 아니라 카드 제목 옆에 설 때는 sm 으로 한 단계 낮춥니다. */
  size?: 'md' | 'sm'
  className?: string
}

export default function Tabs<T extends string>({
  items,
  value,
  onChange,
  label,
  variant = 'pill',
  size = 'md',
  className,
}: Props<T>) {
  // 링크는 눌리면 다른 주소로 떠납니다. 낭독기가 '탭' 으로 읽으면 그 자리에서
  // 내용만 바뀔 것처럼 안내하게 되므로, 그리는 방식에 따라 역할을 가릅니다.
  const asLinks = items.every((item) => item.to !== undefined)

  const root = [styles.root, styles[variant], size === 'sm' && styles.sm, className]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={root} role={asLinks ? 'group' : 'tablist'} aria-label={label}>
      {items.map((item) => {
        const on = item.value === value
        const className = [styles.tab, on ? styles.isActive : ''].filter(Boolean).join(' ')
        const body = (
          <>
            {item.tone && <i className={`${styles.dot} ${styles[item.tone]}`} aria-hidden="true" />}
            {item.icon}
            {item.label}
            {item.count !== undefined && (
              <span className={`${styles.count} tnum`}>{item.count}</span>
            )}
          </>
        )

        return item.to !== undefined ? (
          <Link
            key={item.value}
            to={item.to}
            className={className}
            aria-current={on ? 'page' : undefined}
          >
            {body}
          </Link>
        ) : (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={on}
            className={className}
            onClick={() => onChange?.(item.value)}
          >
            {body}
          </button>
        )
      })}
    </div>
  )
}
