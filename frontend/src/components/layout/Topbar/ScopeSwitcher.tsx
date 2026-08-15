// 팀장이 보는 범위를 고르는 스위처. 고른 값은 화면을 옮겨도 유지됩니다.
//
// FilterSelect 와 생김새는 같지만 동작이 다릅니다. 여러 명을 겹쳐 고를 수 있어야 해서
// 고를 때마다 닫히지 않고, '팀 전체'만 배타적입니다. 그래서 별도 컴포넌트로 둡니다.
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'

import { useCurrentUser } from '@/auth/sessionContext'
import { CheckIcon, ChevronDownIcon } from '@/components/icons'
import { TEAM } from '@/shared/team'
import { SCOPE_ME, SCOPE_TEAM, useOwnerScope } from '@/scope/scopeContext'

import styles from './ScopeSwitcher.module.scss'

export default function ScopeSwitcher() {
  const { profile } = useCurrentUser()
  const { scope, setScope } = useOwnerScope()

  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)

  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([])
  const listboxId = `scope-${useId().replaceAll(':', '')}`

  // 본인은 '내 현황'이 대신하므로 이름으로 한 번 더 넣지 않습니다.
  // 첫 항목의 빈 value 가 '팀 전체'입니다(고른 사람 없음).
  const options = useMemo(
    () => [
      { value: '', label: '팀 전체' },
      { value: SCOPE_ME, label: '내 현황' },
      ...TEAM.filter((member) => member.active && member.name !== profile.name).map((member) => ({
        value: member.id,
        label: member.name,
      })),
    ],
    [profile.name],
  )

  const isTeamAll = scope.length === 0
  const isOn = (value: string) => (value === '' ? isTeamAll : scope.includes(value))

  // 0명이면 팀 전체, 1명이면 그 이름, 2명 이상이면 첫 이름에 나머지 수를 답니다.
  const triggerLabel = useMemo(() => {
    if (isTeamAll) return '팀 전체'
    const labels = scope.map(
      (value) => options.find((option) => option.value === value)?.label ?? value,
    )
    return labels.length === 1 ? labels[0] : `${labels[0]} 외 ${labels.length - 1}명`
  }, [isTeamAll, scope, options])

  // 열면 첫 항목에 섭니다. 여럿을 고를 수 있어 '지금 고른 것' 한 자리가 없습니다.
  useEffect(() => {
    if (!open) return

    setActiveIndex(0)
    const frame = requestAnimationFrame(() => optionRefs.current[0]?.focus())

    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }

    document.addEventListener('pointerdown', onPointerDown)
    return () => {
      cancelAnimationFrame(frame)
      document.removeEventListener('pointerdown', onPointerDown)
    }
  }, [open])

  const focusOption = (index: number) => {
    setActiveIndex(index)
    optionRefs.current[index]?.focus()
  }

  const closeAndFocusTrigger = () => {
    setOpen(false)
    requestAnimationFrame(() => triggerRef.current?.focus())
  }

  /**
   * '팀 전체'는 나머지를 모두 비웁니다. 개별 항목은 겹쳐 고르되, 마지막 하나까지
   * 풀면 다시 팀 전체입니다 — 아무도 없는 범위는 빈 화면일 뿐입니다.
   */
  const toggle = (value: string) => {
    if (value === '') {
      setScope(SCOPE_TEAM)
      return
    }
    setScope(scope.includes(value) ? scope.filter((v) => v !== value) : [...scope, value])
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Tab' && open) {
      setOpen(false)
      return
    }

    if (event.key === 'Escape' && open) {
      event.preventDefault()
      closeAndFocusTrigger()
      return
    }

    if (!open) {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault()
        setOpen(true)
      }
      return
    }

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const delta = event.key === 'ArrowDown' ? 1 : -1
      focusOption((activeIndex + delta + options.length) % options.length)
      return
    }

    if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      focusOption(event.key === 'Home' ? 0 : options.length - 1)
    }
  }

  return (
    <div className={styles.root} ref={rootRef} onKeyDown={onKeyDown}>
      <button
        ref={triggerRef}
        type="button"
        className={`${styles.trigger} ${open ? styles.isOpen : ''}`}
        aria-label={`보기 범위: ${triggerLabel}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        onClick={() => setOpen(!open)}
      >
        <span className={styles.label}>{triggerLabel}</span>
        <ChevronDownIcon className={styles.chevron} width={14} height={14} />
      </button>

      {open && (
        <div
          id={listboxId}
          className={styles.menu}
          role="listbox"
          aria-multiselectable
          aria-label="보기 범위"
        >
          {options.map((option, index) => {
            const on = isOn(option.value)

            return (
              <button
                key={option.value}
                ref={(node) => {
                  optionRefs.current[index] = node
                }}
                type="button"
                role="option"
                aria-selected={on}
                tabIndex={index === activeIndex ? 0 : -1}
                // '팀 전체'와 사람 목록 사이에 선을 하나 둡니다. 성격이 다른 선택입니다.
                className={[
                  styles.option,
                  index === activeIndex ? styles.isActive : '',
                  on ? styles.isOn : '',
                  option.value === SCOPE_ME ? styles.startsGroup : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                onFocus={() => setActiveIndex(index)}
                onPointerMove={() => setActiveIndex(index)}
                onClick={() => toggle(option.value)}
              >
                <span className={`${styles.box} ${on ? styles.isChecked : ''}`} aria-hidden>
                  <CheckIcon width={11} height={11} />
                </span>
                <span>{option.label}</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
