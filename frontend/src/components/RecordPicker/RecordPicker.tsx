// 서버에서 검색해 한 건을 고르는 입력입니다.
//
// 제품·딜·담당자처럼 후보가 계속 늘어나는 목록에 씁니다. 열 때 한 쪽만 받고 목록 끝까지
// 내리면 다음 쪽을 이어 붙이므로, 후보가 수천이어도 첫 응답 크기가 같습니다.
//
// 고객사는 "직접 등록하기" 가 따로 있어 CompanyAutocomplete 를 그대로 씁니다.
import { type KeyboardEvent, useEffect, useId, useMemo, useRef, useState } from 'react'

import { ComboMenu, menuPosition } from '@/components/ComboBox'
import HighlightedText from '@/components/HighlightedText'
import { CloseIcon, SearchIcon } from '@/components/icons'
import useSearchPaging from '@/hooks/useSearchPaging'

import styles from './RecordPicker.module.scss'

/** 고른 한 건. 폼은 id 만 쓰지만 입력칸에 이름을 남겨야 해 label 을 함께 듭니다. */
export interface RecordOption {
  id: string
  label: string
  /** 같은 이름이 섞일 때 오른쪽에 붙는 구분값. 번호나 상태 같은 것입니다. */
  note?: string
}

interface Props<T> {
  /** 조회할 목록. '/products' 처럼 client 의 baseURL 뒤에 붙습니다. */
  path: string
  value: RecordOption | null
  /** 고른 값과 그 원본 행. 목록이 준 다른 칸까지 써야 하는 화면이 row 를 씁니다. */
  onChange: (next: RecordOption | null, row: T | null) => void
  toOption: (row: T) => RecordOption
  /** 조회에 늘 붙는 조건. 값이 바뀌면 처음부터 다시 받습니다. */
  params?: Record<string, unknown>
  disabled?: boolean
  invalid?: boolean
  placeholder?: string
  emptyText?: string
  loadingText?: string
  fallback: string
  /** 화면 낭독기가 읽을 이름 */
  label: string
  id?: string
}

export default function RecordPicker<T>({
  path,
  value,
  onChange,
  toOption,
  params,
  disabled = false,
  invalid = false,
  placeholder = '이름으로 검색',
  emptyText = '일치하는 항목이 없습니다.',
  loadingText = '목록을 불러오는 중입니다.',
  fallback,
  label,
  id,
}: Props<T>) {
  const [query, setQuery] = useState(() => value?.label ?? '')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const generatedId = `records-${useId().replaceAll(':', '')}`
  const listboxId = id ?? generatedId

  const { matches, loading, loadingMore, loadError, hasMore, loadMore, reload } =
    useSearchPaging<T>(path, query, { open, params, enabled: !disabled, fallback })

  const options = useMemo(() => matches.map(toOption), [matches, toOption])

  // 부모가 값을 넣어 주면(수정 화면) 입력칸도 따라갑니다. null 로 비는 경우는 따라가지
  // 않습니다. 고른 뒤 글자를 고치면 선택이 풀리는데, 그때 입력칸까지 지우면 방금 친
  // 글자가 사라집니다. 비우기는 ⓧ 가 맡습니다.
  useEffect(() => {
    if (value !== null) setQuery(value.label)
  }, [value])
  useEffect(() => setActive(0), [options])

  const trimmed = query.trim()

  const choose = (index: number) => {
    const option = options[index]
    onChange(option, matches[index])
    setQuery(option.label)
    setOpen(false)
  }

  const clear = () => {
    setQuery('')
    onChange(null, null)
    setOpen(true)
    inputRef.current?.focus()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape' && open) {
      // 모달까지 올라가면 폼이 통째로 닫힙니다. 목록만 닫습니다.
      event.stopPropagation()
      setOpen(false)
      return
    }

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!open) {
        setOpen(true)
        return
      }
      if (options.length === 0) return
      const delta = event.key === 'ArrowDown' ? 1 : -1
      setActive((previous) => (previous + delta + options.length) % options.length)
      return
    }

    if (event.key === 'Enter' && open && options[active] !== undefined) {
      event.preventDefault()
      choose(active)
    }
  }

  const activeOption = options[active]
  const activeId =
    open && activeOption !== undefined ? `${listboxId}-${activeOption.id}` : undefined

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
        className={[styles.box, disabled ? styles.isDisabled : ''].filter(Boolean).join(' ')}
      >
        <input
          ref={inputRef}
          value={query}
          placeholder={placeholder}
          aria-label={label}
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          aria-controls={open ? listboxId : undefined}
          aria-activedescendant={activeId}
          aria-invalid={invalid ? true : undefined}
          autoComplete="off"
          disabled={disabled}
          maxLength={254}
          onChange={(event) => {
            setQuery(event.target.value)
            // 글자를 고치면 고른 항목과 어긋납니다. 다시 고르게 둡니다.
            if (value !== null) onChange(null, null)
            setActive(0)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
        />

        {query !== '' && !disabled && (
          <button
            type="button"
            className={styles.iconButton}
            aria-label={`${label} 입력 지우기`}
            tabIndex={-1}
            onMouseDown={(event) => event.preventDefault()}
            onClick={clear}
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
          loadingText={loadingText}
          loadError={loadError}
          onRetry={reload}
          empty={options.length === 0}
          emptyText={emptyText}
          hasMore={hasMore}
          loadingMore={loadingMore}
          onReachEnd={loadMore}
        >
          {options.map((option, index) => (
            <button
              key={option.id}
              id={`${listboxId}-${option.id}`}
              type="button"
              role="option"
              aria-selected={value?.id === option.id}
              className={[styles.option, index === active ? styles.isActive : '']
                .filter(Boolean)
                .join(' ')}
              onPointerMove={() => setActive(index)}
              // 목록은 입력칸 밖(body)에 있어, 누르는 순간 포커스가 빠지면 클릭이 닿기 전에
              // 닫힙니다. 포커스를 입력에 붙들어 둡니다.
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(index)}
            >
              <b>
                <HighlightedText text={option.label} query={trimmed} />
              </b>
              {option.note !== undefined && <span>{option.note}</span>}
            </button>
          ))}
        </ComboMenu>
      )}
    </div>
  )
}
