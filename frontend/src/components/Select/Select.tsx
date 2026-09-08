// 검색 없이 정해진 항목 중 하나를 고르는 입력입니다.
//
// 브라우저 기본 select 는 목록을 OS 가 그려서 앱과 모양이 어긋납니다. 목록을 우리가 그리면
// 여백·글꼴·모서리가 다른 화면과 같아집니다. 검색해서 고르는 자리는 RecordPicker 를 씁니다.
import { useEffect, useId, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'

import menuPosition from '@/components/ComboBox/menuPosition'
import { CheckIcon, ChevronDownIcon } from '@/components/icons'

import styles from './Select.module.scss'

export interface SelectOption {
  value: string
  label: string
  disabled?: boolean
}

interface Props {
  /** 화면 낭독기가 읽을 이름 */
  label: string
  value: string
  options: readonly SelectOption[]
  onChange: (value: string) => void
  /** value 가 어느 항목과도 맞지 않을 때 보일 글자 */
  placeholder?: string
  disabled?: boolean
  invalid?: boolean
  /** 표나 좁은 줄에서 쓰는 작은 크기 */
  size?: 'md' | 'sm'
  className?: string
  id?: string
}

export default function Select({
  label,
  value,
  options,
  onChange,
  placeholder = '선택하세요',
  disabled = false,
  invalid = false,
  size = 'md',
  className,
  id,
}: Props) {
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([])
  const generatedId = `select-${useId().replaceAll(':', '')}`
  const listboxId = id ?? generatedId

  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<CSSProperties>()

  const selectedIndex = options.findIndex((option) => option.value === value)
  const [activeIndex, setActiveIndex] = useState(Math.max(0, selectedIndex))

  // 열 때 한 번 자리를 잡고, 고른 항목(없으면 첫 줄)으로 포커스를 옮깁니다.
  useEffect(() => {
    if (!open) return

    const start = Math.max(0, selectedIndex)
    setActiveIndex(start)
    const frame = requestAnimationFrame(() => optionRefs.current[start]?.focus())

    // 목록은 body 로 나가 있어 트리거 안에 없습니다. 두 곳 다 확인해야 바깥 클릭을 가립니다.
    //
    // 캡처 단계로 듣습니다. 모달·드로어 본문은 스크림까지 눌림이 번지지 않게
    // pointerdown 을 멈추는데(Modal.tsx, Drawer.tsx), React 는 listener 를 루트에 걸어 두어
    // 거기서 멈추면 document 까지 오지 않습니다. 캡처는 그보다 먼저 지나갑니다.
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (triggerRef.current?.contains(target)) return
      if (menuRef.current?.contains(target)) return
      setOpen(false)
    }

    // 좌표는 열 때 한 번만 재므로, 화면이 움직이면 목록만 제자리에 남습니다. 그럴 땐 닫습니다.
    const close = () => setOpen(false)

    document.addEventListener('pointerdown', onPointerDown, true)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    return () => {
      cancelAnimationFrame(frame)
      document.removeEventListener('pointerdown', onPointerDown, true)
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
    }
  }, [open, selectedIndex])

  const openMenu = () => {
    const place = menuPosition(triggerRef.current)
    // menuPosition 은 트리거 너비를 그대로 씁니다. 검색 입력은 늘 폼 한 칸을 다 쓰지만
    // 여기 트리거는 고른 값만큼만 좁을 수 있어, 그대로 두면 긴 항목이 잘립니다.
    // 트리거보다 좁아지지 않되 항목 이름만큼 넓어지게 하고, 화면 밖으로는 못 나가게 막습니다.
    setPosition(
      place && {
        ...place,
        width: 'max-content',
        minWidth: place.width,
        maxWidth: window.innerWidth - Number(place.left ?? 0) - 8,
      },
    )
    setOpen(true)
  }

  const closeAndFocusTrigger = () => {
    setOpen(false)
    requestAnimationFrame(() => triggerRef.current?.focus())
  }

  const focusOption = (index: number) => {
    setActiveIndex(index)
    optionRefs.current[index]?.focus()
  }

  const choose = (index: number) => {
    const option = options[index]
    if (!option || option.disabled) return
    onChange(option.value)
    closeAndFocusTrigger()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return

    if (event.key === 'Tab' && open) {
      setOpen(false)
      return
    }

    if (event.key === 'Escape' && open) {
      event.preventDefault()
      // 모달 안에서 쓰면 Escape 가 위로 올라가 모달까지 닫습니다. 목록만 닫습니다.
      event.stopPropagation()
      closeAndFocusTrigger()
      return
    }

    if (!open) {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault()
        openMenu()
      }
      return
    }

    if (options.length === 0) return

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const delta = event.key === 'ArrowDown' ? 1 : -1
      focusOption((activeIndex + delta + options.length) % options.length)
      return
    }

    if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      focusOption(event.key === 'Home' ? 0 : options.length - 1)
      return
    }

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      choose(activeIndex)
    }
  }

  const selected = selectedIndex === -1 ? null : options[selectedIndex]

  return (
    <div
      className={[styles.root, size === 'sm' ? styles.isSmall : '', className]
        .filter(Boolean)
        .join(' ')}
      onKeyDown={onKeyDown}
    >
      <button
        ref={triggerRef}
        type="button"
        className={[
          styles.trigger,
          open ? styles.isOpen : '',
          invalid ? styles.isInvalid : '',
          selected ? '' : styles.isPlaceholder,
        ]
          .filter(Boolean)
          .join(' ')}
        disabled={disabled}
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        aria-invalid={invalid || undefined}
        onClick={() => (open ? setOpen(false) : openMenu())}
      >
        <span className={styles.value}>{selected?.label ?? placeholder}</span>
        <ChevronDownIcon className={styles.chevron} width={16} height={16} />
      </button>

      {open &&
        createPortal(
          <div
            ref={menuRef}
            id={listboxId}
            className={styles.menu}
            style={position}
            role="listbox"
            aria-label={label}
          >
            {options.map((option, index) => {
              const isSelected = index === selectedIndex
              const isActive = index === activeIndex

              return (
                <button
                  key={option.value}
                  ref={(node) => {
                    optionRefs.current[index] = node
                  }}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  disabled={option.disabled}
                  tabIndex={isActive ? 0 : -1}
                  className={[
                    styles.option,
                    isActive ? styles.isActive : '',
                    isSelected ? styles.isSelected : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onFocus={() => setActiveIndex(index)}
                  onPointerMove={() => setActiveIndex(index)}
                  // 목록이 트리거 밖에 있어, 누르는 순간 포커스가 빠지면 클릭이 닿기 전에 닫힙니다.
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => choose(index)}
                >
                  <span className={styles.optionLabel}>{option.label}</span>
                  <CheckIcon
                    className={`${styles.check} ${isSelected ? '' : styles.isHidden}`}
                    width={14}
                    height={14}
                  />
                </button>
              )
            })}
          </div>,
          document.body,
        )}
    </div>
  )
}
