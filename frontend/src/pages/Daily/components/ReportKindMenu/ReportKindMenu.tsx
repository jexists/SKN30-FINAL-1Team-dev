// "보고서 작성하기" 버튼에 붙는 드롭다운입니다.
//
// 보고는 아래에서 위로 쌓입니다. 일정을 업무보고서로 남기고, 하루를 일일보고로 묶고,
// 한 주를 주간으로, 한 달을 월간으로 올립니다. 종류마다 자료가 다르므로 무엇을 쓸지
// 고르면 그에 맞는 자료 선택 화면으로 보냅니다.
//
// 종류가 이미 정해진 기간 탭에서는 이 메뉴를 거치지 않고 바로 넘어갑니다(Daily.tsx).
import { useRef, useState, type KeyboardEvent } from 'react'

import Button from '@/components/Button'
import Popover from '@/components/Popover'
import { ChevronDownIcon } from '@/components/icons'
import type { ReportKind } from '@/types'

import styles from './ReportKindMenu.module.scss'

/** 업무보고서는 ReportKind 가 아니라 일정 하나에 붙는 별도 모델입니다. */
export type ComposeKind = ReportKind | '미팅'

interface Option {
  kind: ComposeKind
  title: string
  desc: string
}

const OPTIONS: Option[] = [
  { kind: '미팅', title: '업무보고서', desc: '일정 1건을 선택해 기록합니다.' },
  { kind: '일일', title: '일일업무', desc: '오늘의 일정과 미팅 결과를 모아 작성합니다.' },
  { kind: '주간', title: '주간업무', desc: '제출된 일일업무보고서를 모아 작성합니다.' },
  { kind: '월간', title: '월간업무', desc: '제출된 주간업무보고서를 모아 작성합니다.' },
]

interface Props {
  onSelect: (kind: ComposeKind) => void
}

export default function ReportKindMenu({ onSelect }: Props) {
  const [open, setOpen] = useState(false)
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([])

  // 위아래 화살표로 항목을 옮겨 다닙니다. 여닫기와 Escape 는 Popover 가 봅니다.
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
    event.preventDefault()
    const delta = event.key === 'ArrowDown' ? 1 : -1
    itemRefs.current[(index + delta + OPTIONS.length) % OPTIONS.length]?.focus()
  }

  return (
    <Popover
      open={open}
      onClose={() => setOpen(false)}
      align="end"
      compact
      label="보고서 종류"
      trigger={
        <Button
          type="button"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          보고서 작성하기
          <ChevronDownIcon />
        </Button>
      }
    >
      <div className={styles.menu} role="menu" aria-label="보고서 종류">
        {OPTIONS.map((option, index) => (
          <button
            key={option.kind}
            ref={(node) => {
              itemRefs.current[index] = node
            }}
            type="button"
            role="menuitem"
            className={styles.item}
            // 열자마자 첫 항목에서 타이핑할 수 있게 포커스를 옮깁니다.
            autoFocus={index === 0}
            onKeyDown={(event) => onKeyDown(event, index)}
            onClick={() => {
              setOpen(false)
              onSelect(option.kind)
            }}
          >
            <strong className={styles.title}>{option.title}</strong>
            <span className={styles.desc}>{option.desc}</span>
          </button>
        ))}
      </div>
    </Popover>
  )
}
