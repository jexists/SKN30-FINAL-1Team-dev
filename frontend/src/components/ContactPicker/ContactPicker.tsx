// 고객사에 속한 담당자를 검색해서 고르는 입력입니다.
//
// 회사를 먼저 고르고 그 안에서 사람을 찾습니다. 같은 이름이 흔해 사람부터 찾으면 누구인지
// 가려내기 어렵고, 영업은 회사를 먼저 떠올리기 때문입니다. 한 명만 받는 칸과 여러 명을 칩으로
// 담는 칸이 하는 일이 같아 multiple 하나로 가릅니다.
import { type KeyboardEvent, useEffect, useId, useRef, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import { ComboMenu, menuPosition } from '@/components/ComboBox'
import HighlightedText from '@/components/HighlightedText'
import { CloseIcon, InfoIcon, SearchIcon } from '@/components/icons'
import useDebouncedValue from '@/hooks/useDebouncedValue'
import type { CustomerContactResponse, PageResponse } from '@/types'

import { toContactOption, type ContactOption } from './contactOption'

import styles from './ContactPicker.module.scss'

interface CommonProps {
  /** 고른 고객사. 없으면 고를 것이 없으므로 칸이 잠깁니다. */
  companyId: string | null
  /** 목록에 없을 때 직접 등록하는 줄을 띄울지. 조회 전용 화면에서는 끕니다. */
  allowCreate?: boolean
  /** 그 줄을 눌렀을 때. 지금까지 친 이름을 그대로 넘깁니다. */
  onCreate?: (name: string) => void
  disabled?: boolean
  invalid?: boolean
  placeholder?: string
  /** 화면 낭독기가 읽을 이름 */
  label?: string
  id?: string
}

type Props = CommonProps &
  (
    | {
        multiple?: false
        value: ContactOption | null
        onChange: (next: ContactOption | null) => void
      }
    | { multiple: true; value: ContactOption[]; onChange: (next: ContactOption[]) => void }
  )

const MAX_MATCHES = 8

function useContactSearch(companyId: string | null, query: string, open: boolean) {
  const [matches, setMatches] = useState<ContactOption[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const settledQuery = useDebouncedValue(query.trim())

  useEffect(() => {
    // 닫혀 있거나 회사를 아직 고르지 않았으면 부를 이유가 없습니다.
    if (!open || companyId === null) return

    const controller = new AbortController()
    setLoading(true)
    setLoadError(null)

    void client
      .get<PageResponse<CustomerContactResponse>>('/customer-contacts', {
        params: {
          company_id: companyId,
          q: settledQuery === '' ? undefined : settledQuery.slice(0, 100),
          skip: 0,
          limit: MAX_MATCHES,
        },
        signal: controller.signal,
      })
      .then(({ data }) => {
        if (!controller.signal.aborted) setMatches(data.items.map(toContactOption))
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return
        setMatches([])
        setLoadError(errorMessage(reason, '고객을 불러오지 못했습니다.'))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [companyId, settledQuery, open, reloadKey])

  return { matches, loading, loadError, reload: () => setReloadKey((value) => value + 1) }
}

/** 칩에 적는 이름. 같은 이름이 섞여도 직함까지 보면 구분이 됩니다. */
function chipLabel(contact: ContactOption): string {
  return [contact.name, contact.title].filter(Boolean).join(' ')
}

export default function ContactPicker(props: Props) {
  const {
    companyId,
    allowCreate = false,
    onCreate,
    disabled = false,
    invalid = false,
    placeholder = '이름으로 검색',
    label = '고객',
    id,
  } = props

  const chips = props.multiple ? props.value : props.value ? [props.value] : []

  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const generatedId = `contacts-${useId().replaceAll(':', '')}`
  const listboxId = id ?? generatedId

  const locked = disabled || companyId === null
  const { matches, loading, loadError, reload } = useContactSearch(
    companyId,
    query,
    open && !locked,
  )

  // 회사를 바꾸면 앞서 치던 글자는 다른 회사의 것입니다.
  useEffect(() => setQuery(''), [companyId])
  useEffect(() => setActive(0), [matches])

  const trimmed = query.trim()
  // 여러 명을 담는 칸에서는 이미 담은 사람을 후보에서 뺍니다. 한 명만 받는 칸은
  // 고른 사람도 남겨 두어야 지금 무엇이 골라져 있는지 목록에서 보입니다.
  const taken = new Set(props.multiple ? props.value.map((contact) => contact.id) : [])
  const found = matches.filter((contact) => !taken.has(contact.id))

  // 같은 이름이 이미 있으면 또 만들자고 권하지 않습니다. 회사를 고르기 전에는 목록
  // 자체가 열리지 않으므로 이 줄도 없습니다.
  const hasExactMatch = matches.some((contact) => contact.name === trimmed)
  const creatable =
    allowCreate && onCreate !== undefined && !hasExactMatch && !loading && loadError === null
  const options: (ContactOption | 'create')[] = creatable ? [...found, 'create'] : found

  const choose = (option: ContactOption | 'create') => {
    if (option === 'create') {
      onCreate?.(trimmed)
      setOpen(false)
      return
    }
    const contact = option
    if (props.multiple) {
      props.onChange([...props.value, contact])
      setQuery('')
      inputRef.current?.focus()
    } else {
      props.onChange(contact)
      setOpen(false)
    }
  }

  const remove = (contactId: string) => {
    if (props.multiple) props.onChange(props.value.filter((contact) => contact.id !== contactId))
    else props.onChange(null)
    inputRef.current?.focus()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape' && open) {
      // 모달까지 올라가면 폼이 통째로 닫힙니다. 목록만 닫습니다.
      event.stopPropagation()
      setOpen(false)
      return
    }

    // 빈 칸에서 지우면 마지막으로 담은 사람을 뺍니다. 칩 UI 의 관례입니다.
    if (event.key === 'Backspace' && query === '' && chips.length > 0) {
      event.preventDefault()
      remove(chips[chips.length - 1].id)
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

    if (event.key === 'Enter' && open && options[active]) {
      event.preventDefault()
      choose(options[active])
    }
  }

  const emptyText =
    trimmed !== ''
      ? '일치하는 고객이 없습니다.'
      : matches.length > 0
        ? '남은 고객이 없습니다.'
        : '이 고객사에 등록된 고객이 없습니다.'

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
        className={[
          styles.box,
          chips.length > 0 ? styles.hasChips : '',
          locked ? styles.isDisabled : '',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <div className={styles.chips}>
          {chips.map((contact) => (
            <span key={contact.id} className={styles.chip}>
              {chipLabel(contact)}
              {!locked && (
                <button
                  type="button"
                  className={styles.chipRemove}
                  aria-label={`${contact.name} 빼기`}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => remove(contact.id)}
                >
                  <CloseIcon width={12} height={12} />
                </button>
              )}
            </span>
          ))}

          <input
            ref={inputRef}
            value={query}
            placeholder={
              companyId === null ? '고객사를 먼저 고르세요' : chips.length === 0 ? placeholder : ''
            }
            aria-label={label}
            role="combobox"
            aria-expanded={open}
            aria-autocomplete="list"
            aria-controls={open ? listboxId : undefined}
            aria-activedescendant={activeId}
            aria-invalid={invalid ? true : undefined}
            autoComplete="off"
            disabled={locked}
            onChange={(event) => {
              setQuery(event.target.value)
              setOpen(true)
            }}
            onFocus={() => setOpen(true)}
          />
        </div>

        {query !== '' && !locked && (
          <button
            type="button"
            className={styles.iconButton}
            aria-label="고객 검색어 지우기"
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

      {open && !locked && (
        <ComboMenu
          id={listboxId}
          label={label}
          style={menuPosition(boxRef.current)}
          loading={loading}
          loadingText="고객을 불러오는 중입니다."
          loadError={loadError}
          onRetry={reload}
          empty={found.length === 0}
          emptyText={emptyText}
          footer={
            creatable && (
              <button
                id={`${listboxId}-create`}
                type="button"
                role="option"
                aria-selected={false}
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
                <span>
                  {trimmed === ''
                    ? '이 고객사에 고객 등록하기'
                    : `"${trimmed}"(으)로 직접 등록하기`}
                </span>
              </button>
            )
          }
        >
          {found.map((contact, index) => (
            <button
              key={contact.id}
              id={`${listboxId}-${contact.id}`}
              type="button"
              role="option"
              aria-selected={!props.multiple && props.value?.id === contact.id}
              className={[styles.option, index === active ? styles.isActive : '']
                .filter(Boolean)
                .join(' ')}
              onPointerMove={() => setActive(index)}
              // 목록은 입력칸 밖(body)에 있어, 누르는 순간 포커스가 빠지면
              // 클릭이 닿기 전에 닫힙니다. 포커스를 입력에 붙들어 둡니다.
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(contact)}
            >
              <b>
                <HighlightedText text={contact.name} query={trimmed} />
              </b>
              <span>{[contact.dept, contact.title].filter(Boolean).join(' · ')}</span>
            </button>
          ))}
        </ComboMenu>
      )}
    </div>
  )
}
