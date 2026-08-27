// 고객사를 검색해서 고르는 입력입니다.
//
// 회사를 미리 등록해 두는 화면은 없습니다. 목록에 없으면 마지막 줄의 "직접 등록하기"로
// 그 자리에서 고릅니다. 실제 생성은 폼을 제출할 때 일어나므로, 고르고 나서 취소해도
// 빈 고객사가 남지 않습니다.
import { type KeyboardEvent, useEffect, useId, useRef, useState } from 'react'

import { ComboMenu, menuPosition } from '@/components/ComboBox'
import HighlightedText from '@/components/HighlightedText'
import { CloseIcon, InfoIcon, SearchIcon } from '@/components/icons'
import useSearchPaging from '@/hooks/useSearchPaging'
import type { CustomerCompanyResponse } from '@/types'
import { formatBusinessNo } from '@/utils/format'

import styles from './CompanyAutocomplete.module.scss'

/** 고른 결과. 이미 있는 고객사이거나, 아직 만들지 않은 새 고객사입니다. */
export type CompanySelection =
  { kind: 'existing'; company: CustomerCompanyResponse } | { kind: 'new'; name: string }

interface Props {
  value: CompanySelection | null
  onChange: (selection: CompanySelection | null) => void
  /** 목록에 없을 때 직접 등록하는 줄을 띄울지. 조회 전용 화면에서는 끕니다. */
  allowCreate?: boolean
  disabled?: boolean
  invalid?: boolean
  placeholder?: string
  /** 화면 낭독기가 읽을 이름 */
  label?: string
  id?: string
}

/** 고른 값이 없을 때도 입력칸에 남아야 하는 글자입니다. */
function selectionName(selection: CompanySelection | null): string {
  if (selection === null) return ''
  return selection.kind === 'existing' ? selection.company.name : selection.name
}

export default function CompanyAutocomplete({
  value,
  onChange,
  allowCreate = false,
  disabled = false,
  invalid = false,
  placeholder = '회사 이름으로 검색',
  label = '회사',
  id,
}: Props) {
  const [query, setQuery] = useState(() => selectionName(value))
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const generatedId = `companies-${useId().replaceAll(':', '')}`
  const listboxId = id ?? generatedId

  const { matches, loading, loadingMore, loadError, hasMore, loadMore, reload } =
    useSearchPaging<CustomerCompanyResponse>('/customer-companies', query, {
      open,
      fallback: '고객사를 불러오지 못했습니다.',
    })

  // 부모가 값을 넣어 주면(수정 화면) 입력칸도 따라갑니다.
  // null 로 비는 경우는 따라가지 않습니다. 고른 뒤 글자를 고치면 선택이 풀리는데,
  // 그때 입력칸까지 지우면 방금 친 글자가 사라집니다. 비우기는 ⓧ 가 맡습니다.
  useEffect(() => {
    if (value !== null) setQuery(selectionName(value))
  }, [value])
  useEffect(() => setActive(0), [matches])

  const trimmed = query.trim()
  const hasExactMatch = matches.some((company) => company.name === trimmed)
  const creatable = allowCreate && trimmed !== '' && !hasExactMatch && !loading && !loadError
  const duplicated = new Set(
    matches
      .map((company) => company.name)
      .filter((name, index, names) => names.indexOf(name) !== index),
  )
  // 회사명 옆 회색 한 마디. 주소가 어느 회사인지 가장 빨리 알려 주고, 주소가 없을 때만
  // 같은 이름을 사업자등록번호로 가릅니다. 어느 쪽이든 줄은 하나입니다.
  const hint = (company: CustomerCompanyResponse): string | null => {
    if (company.address !== null) return company.address
    if (!duplicated.has(company.name)) return null
    return formatBusinessNo(company.business_no) ?? '사업자번호 없음'
  }
  const options: (CustomerCompanyResponse | 'create')[] = creatable
    ? [...matches, 'create']
    : matches

  const choose = (option: CustomerCompanyResponse | 'create') => {
    if (option === 'create') {
      onChange({ kind: 'new', name: trimmed })
      setQuery(trimmed)
    } else {
      onChange({ kind: 'existing', company: option })
      setQuery(option.name)
    }
    setOpen(false)
  }

  const clear = () => {
    setQuery('')
    onChange(null)
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
      choose(options[active])
    }
  }

  const activeOption = options[active]
  const activeId =
    open && activeOption !== undefined
      ? `${listboxId}-${activeOption === 'create' ? 'create' : activeOption.id}`
      : undefined

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
            // 글자를 고치면 고른 회사와 어긋납니다. 다시 고르게 둡니다.
            if (value !== null) onChange(null)
            setActive(0)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
        />

        {query !== '' && !disabled && (
          <button
            type="button"
            className={styles.iconButton}
            aria-label="회사 입력 지우기"
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
          loadingText="고객사를 불러오는 중입니다."
          loadError={loadError}
          onRetry={reload}
          empty={matches.length === 0}
          emptyText="일치하는 고객사가 없습니다."
          hasMore={hasMore}
          loadingMore={loadingMore}
          onReachEnd={loadMore}
          footer={
            creatable && (
              <button
                key="create"
                id={`${listboxId}-create`}
                type="button"
                role="option"
                aria-selected={value?.kind === 'new'}
                className={[
                  styles.option,
                  styles.createOption,
                  activeOption === 'create' ? styles.isActive : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                onPointerMove={() => setActive(options.length - 1)}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose('create')}
              >
                <InfoIcon width={14} height={14} />
                <span>&quot;{trimmed}&quot;(으)로 직접 등록하기</span>
              </button>
            )
          }
        >
          {matches.map((company, index) => (
            <button
              key={company.id}
              id={`${listboxId}-${company.id}`}
              type="button"
              role="option"
              aria-selected={value?.kind === 'existing' && value.company.id === company.id}
              className={[styles.option, index === active ? styles.isActive : '']
                .filter(Boolean)
                .join(' ')}
              onPointerMove={() => setActive(index)}
              // 목록은 입력칸 밖(body)에 있어, 누르는 순간 포커스가 빠지면
              // 클릭이 닿기 전에 닫힙니다. 포커스를 입력에 붙들어 둡니다.
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(company)}
            >
              <b>
                <HighlightedText text={company.name} query={trimmed} />
              </b>
              {hint(company) !== null && <span>{hint(company)}</span>}
            </button>
          ))}
        </ComboMenu>
      )}
    </div>
  )
}
