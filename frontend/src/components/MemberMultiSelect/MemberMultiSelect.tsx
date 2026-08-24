// 팀원을 여러 명 골라 칩으로 보여 주는 입력입니다.
//
// 팀 하나의 인원이라 목록을 한 번 받아 두고 검색은 화면에서 거릅니다. 고른 순서를 그대로
// 지키므로, 순서에 뜻이 있는 화면(첫 번째가 대표)에서도 그대로 쓸 수 있습니다.
import { type KeyboardEvent, useEffect, useId, useMemo, useRef, useState } from 'react'

import { ComboMenu, menuPosition } from '@/components/ComboBox'
import HighlightedText from '@/components/HighlightedText'
import { CloseIcon, SearchIcon } from '@/components/icons'
import useTeamMembers from '@/hooks/useTeamMembers'
import type { TeamMemberOption } from '@/types'

import styles from './MemberMultiSelect.module.scss'

interface Props {
  /** 고른 팀원의 member id. 배열 순서가 곧 표시 순서입니다. */
  value: string[]
  onChange: (memberIds: string[]) => void
  /** 최대 선택 수. 주지 않으면 제한이 없습니다. */
  max?: number
  disabled?: boolean
  invalid?: boolean
  placeholder?: string
  /** 화면 낭독기가 읽을 이름 */
  label?: string
  /** 첫 번째 칩에 붙일 설명. 순서에 뜻이 있는 화면에서 씁니다. */
  firstChipHint?: string
  id?: string
}

export default function MemberMultiSelect({
  value,
  onChange,
  max,
  disabled = false,
  invalid = false,
  placeholder = '이름으로 검색',
  label = '담당자',
  firstChipHint,
  id,
}: Props) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const generatedId = `members-${useId().replaceAll(':', '')}`
  const listboxId = id ?? generatedId

  // 목록을 한 번 열기 전까지는 부르지 않습니다. 다만 이미 고른 값의 이름은 보여야 하므로
  // 값이 있으면 처음부터 받아 둡니다.
  const { members, loading, loadError, reload } = useTeamMembers(open || value.length > 0)

  useEffect(() => setActive(0), [query, members])

  const memberById = useMemo(() => new Map(members.map((member) => [member.id, member])), [members])
  const chips = value.map((memberId) => memberById.get(memberId) ?? null)

  const trimmed = query.trim()
  const reachedMax = max !== undefined && value.length >= max
  const matches = members.filter(
    (member) =>
      !value.includes(member.id) &&
      (trimmed === '' || member.display_name.toLowerCase().includes(trimmed.toLowerCase())),
  )
  // 같은 이름이 여럿일 때만 직함으로 구분합니다.
  const duplicated = new Set(
    matches
      .map((member) => member.display_name)
      .filter((name, index, names) => names.indexOf(name) !== index),
  )

  const add = (member: TeamMemberOption) => {
    if (reachedMax) return
    onChange([...value, member.id])
    setQuery('')
    inputRef.current?.focus()
  }

  const remove = (memberId: string) => {
    onChange(value.filter((selected) => selected !== memberId))
    inputRef.current?.focus()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape' && open) {
      // 모달까지 올라가면 폼이 통째로 닫힙니다. 목록만 닫습니다.
      event.stopPropagation()
      setOpen(false)
      return
    }

    if (event.key === 'Backspace' && query === '' && value.length > 0) {
      event.preventDefault()
      remove(value[value.length - 1])
      return
    }

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!open) {
        setOpen(true)
        return
      }
      if (matches.length === 0) return
      const delta = event.key === 'ArrowDown' ? 1 : -1
      setActive((previous) => (previous + delta + matches.length) % matches.length)
      return
    }

    if (event.key === 'Enter' && open && matches[active]) {
      event.preventDefault()
      add(matches[active])
    }
  }

  const emptyText = reachedMax
    ? `최대 ${max}명까지 고를 수 있습니다.`
    : members.length === 0
      ? '팀원이 없습니다.'
      : '일치하는 팀원이 없습니다.'

  return (
    <div
      className={styles.root}
      onKeyDown={onKeyDown}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false)
      }}
    >
      <div
        ref={boxRef}
        className={[
          styles.box,
          value.length > 0 ? styles.hasChips : '',
          disabled ? styles.isDisabled : '',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <div className={styles.chips}>
          {chips.map((member, index) => {
            const memberId = value[index]
            const name = member?.display_name ?? (loading ? '불러오는 중…' : '알 수 없는 팀원')
            return (
              <span
                key={memberId}
                className={styles.chip}
                title={index === 0 ? firstChipHint : undefined}
              >
                {name}
                {!disabled && (
                  <button
                    type="button"
                    className={styles.chipRemove}
                    aria-label={`${name} 빼기`}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => remove(memberId)}
                  >
                    <CloseIcon width={12} height={12} />
                  </button>
                )}
              </span>
            )
          })}

          <input
            ref={inputRef}
            value={query}
            placeholder={value.length === 0 ? placeholder : ''}
            aria-label={label}
            role="combobox"
            aria-expanded={open}
            aria-autocomplete="list"
            aria-controls={open ? listboxId : undefined}
            aria-activedescendant={
              open && matches[active] ? `${listboxId}-${matches[active].id}` : undefined
            }
            aria-invalid={invalid ? true : undefined}
            autoComplete="off"
            disabled={disabled}
            onChange={(event) => {
              setQuery(event.target.value)
              setOpen(true)
            }}
            onFocus={() => setOpen(true)}
          />
        </div>

        {query !== '' && !disabled && (
          <button
            type="button"
            className={styles.iconButton}
            aria-label="담당자 검색어 지우기"
            tabIndex={-1}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              setQuery('')
              inputRef.current?.focus()
            }}
          >
            <CloseIcon width={14} height={14} />
          </button>
        )}

        <SearchIcon className={styles.searchIcon} width={16} height={16} />
      </div>

      {open && (
        <ComboMenu
          id={listboxId}
          label={label}
          style={menuPosition(boxRef.current)}
          loading={loading}
          loadingText="팀원을 불러오는 중입니다."
          loadError={loadError}
          onRetry={reload}
          empty={matches.length === 0 || reachedMax}
          emptyText={emptyText}
        >
          {!reachedMax &&
            matches.map((member, index) => (
              <button
                key={member.id}
                id={`${listboxId}-${member.id}`}
                type="button"
                role="option"
                aria-selected={false}
                className={[styles.option, index === active ? styles.isActive : '']
                  .filter(Boolean)
                  .join(' ')}
                onPointerMove={() => setActive(index)}
                // 목록은 입력칸 밖(body)에 있어, 누르는 순간 포커스가 빠지면
                // 클릭이 닿기 전에 닫힙니다. 포커스를 입력에 붙들어 둡니다.
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => add(member)}
              >
                <b>
                  <HighlightedText text={member.display_name} query={trimmed} />
                </b>
                {duplicated.has(member.display_name) && (
                  <span>{member.job_title ?? '직함 없음'}</span>
                )}
              </button>
            ))}
        </ComboMenu>
      )}
    </div>
  )
}
