/**
 * 화면 전체가 누구의 현황을 보고 있는지 고르는 스위처입니다.
 *
 * 팀원에게는 고를 것이 없어 글자만 둡니다. 목록을 감추는 것이 권한은 아니고, 실제
 * 차단은 백엔드가 합니다. 여기서는 팀원에게 고를 수 없는 것을 보여 주지 않을 뿐입니다.
 *
 * 여러 명을 동시에 고를 수 있어야 해서 FilterSelect(단일 선택, 고르면 닫힘)를 그대로
 * 쓰지 못했습니다. 대신 그 파일의 바깥 클릭·Escape·화살표 이동 처리를 옮겨 왔고,
 * 다른 점은 Enter/Space 가 닫지 않고 토글한다는 것뿐입니다.
 *
 * 열려 있는 동안 고른 것은 초안으로만 들고 있다가 닫을 때 한 번에 넘깁니다. 체크마다
 * 바로 넘기면 화면 전체가 그때마다 다시 그려지고 다시 요청합니다. 세 사람을 고르는 것은
 * 한 번의 마음이므로 요청도 한 번이면 됩니다.
 */
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'

import { useCurrentUser } from '@/auth/sessionContext'
import { CheckIcon, ChevronDownIcon } from '@/components/icons'
import useTeamMembers from '@/hooks/useTeamMembers'
import { reconcileScope, type Scope, setScopeAll, setScopeMembers, useScope } from '@/shared/scope'

import styles from './ScopeSwitcher.module.scss'

const ALL_LABEL = '팀 전체'
const ME_LABEL = '내 현황'

interface Row {
  key: string
  label: string
  selected: boolean
  choose: () => void
  /** 팀원 목록 첫 줄 위에 구분선을 둡니다. */
  divided?: boolean
}

export default function ScopeSwitcher() {
  const { isManager, memberId } = useCurrentUser()

  if (!isManager) {
    // 팀원은 언제나 본인 것만 봅니다. 누를 수 없는 표시로 지금 범위만 알립니다.
    return <span className={styles.fixed}>{ME_LABEL}</span>
  }

  return <ManagerScopeSwitcher ownMemberId={memberId} />
}

function ManagerScopeSwitcher({ ownMemberId }: { ownMemberId: string }) {
  const scope = useScope()
  const [open, setOpen] = useState(false)
  // 열려 있는 동안의 초안입니다. null 이면 지금 쓰이고 있는 범위를 그대로 봅니다.
  const [draft, setDraft] = useState<Scope | null>(null)
  const view = draft ?? scope
  // 닫혀 있어도 고른 사람이 있으면 이름을 보여 줘야 하므로 미리 받아 둡니다.
  const { members } = useTeamMembers(open || scope.mode === 'users')

  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([])
  const listboxId = `scope-${useId().replaceAll(':', '')}`
  const [activeIndex, setActiveIndex] = useState(0)

  // 팀에서 빠진 사람이 선택에 남아 있으면 서버가 목록 전체를 거절합니다. 열어 둔 채로
  // 명부가 도착할 수 있으므로 초안도 같은 기준으로 걸러 둡니다.
  useEffect(() => {
    if (members.length === 0) return
    const available = members.map((member) => member.id)
    reconcileScope(available)
    setDraft((current) => {
      if (current === null || current.mode !== 'users') return current
      const next = current.memberIds.filter((id) => available.includes(id))
      if (next.length === current.memberIds.length) return current
      return next.length === 0 ? { mode: 'all', memberIds: [] } : { mode: 'users', memberIds: next }
    })
  }, [members])

  const teamIds = members.map((member) => member.id)
  // '팀 전체' 는 명부 전체를 고른 것과 같습니다. 거기서 한 명만 빼려면 나머지가 이름으로
  // 남아 있어야 하므로, 계산할 때는 팀 전체를 명부로 펼쳐 둡니다.
  const chosen = view.mode === 'all' ? teamIds : view.memberIds
  // 명부가 아직 오지 않았어도 팀 전체면 체크로 보입니다. 뜨는 순간 깜빡이지 않게 합니다.
  const picked = (id: string) => view.mode === 'all' || chosen.includes(id)
  const coversTeam = view.mode === 'all' || (teamIds.length > 0 && teamIds.every(picked))

  const toggle = (id: string) => {
    if (!chosen.includes(id)) {
      setDraft({ mode: 'users', memberIds: [...chosen, id] })
      return
    }
    // 마지막 한 명까지 끄면 볼 것이 없어집니다. 팀 전체로 튕겨 보내는 대신 그 클릭을
    // 받지 않습니다. 한 사람만 보려던 의도가 전체 보기로 뒤집히지 않게 합니다.
    if (chosen.length <= 1) return
    setDraft({ mode: 'users', memberIds: chosen.filter((memberId) => memberId !== id) })
  }

  // 켜져 있을 때 다시 누르면 전부 풀고 본인만 남깁니다. 팀 전체에서 한 사람으로 좁히려고
  // 나머지를 하나씩 끄던 길을 한 번으로 줄입니다. 아무도 없는 상태는 볼 것이 없으므로
  // 만들지 않습니다.
  const chooseAll = () => {
    setDraft(
      coversTeam ? { mode: 'users', memberIds: [ownMemberId] } : { mode: 'all', memberIds: [] },
    )
  }

  const rows: Row[] = [
    { key: 'all', label: ALL_LABEL, selected: coversTeam, choose: chooseAll },
    // 본인은 '내 현황' 한 줄로만 둡니다. 아래 팀원 목록에 또 넣으면 같은 사람이 두 줄이 됩니다.
    {
      key: ownMemberId,
      label: ME_LABEL,
      selected: picked(ownMemberId),
      choose: () => toggle(ownMemberId),
      divided: true,
    },
    ...members
      .filter((member) => member.id !== ownMemberId)
      .map((member) => ({
        key: member.id,
        label: member.display_name,
        selected: picked(member.id),
        choose: () => toggle(member.id),
      })),
  ]

  // 초안을 넘기고 닫습니다. 닫는 길은 모두 여기를 지나므로 취소로 빠지는 문은 없습니다.
  // 이 앱의 다른 필터도 고른 것을 되돌리지 않아, 여기만 다르게 두면 헷갈립니다.
  const close = () => {
    if (draft !== null) {
      if (draft.mode === 'all') setScopeAll()
      else setScopeMembers(draft.memberIds)
      setDraft(null)
    }
    setOpen(false)
  }

  // 바깥 클릭 listener 는 열 때 한 번만 붙는데 초안은 그 뒤로도 바뀌므로, 최신 close 를
  // 여기에 담아 둡니다.
  const closeRef = useRef(close)
  useEffect(() => {
    closeRef.current = close
  })

  // 열 때 맨 위로 잡습니다. 여러 명을 이어서 고르는 동안에는 포커스를 다시 옮기지 않으므로
  // 이 effect 는 open 에만 반응하면 됩니다.
  useEffect(() => {
    if (!open) return

    setActiveIndex(0)
    const frame = requestAnimationFrame(() => optionRefs.current[0]?.focus())

    const onPointerDown = (event: PointerEvent) => {
      // 초안은 매 렌더 바뀌므로 최신 close 를 ref 로 집습니다.
      if (!rootRef.current?.contains(event.target as Node)) closeRef.current()
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
    close()
    requestAnimationFrame(() => triggerRef.current?.focus())
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Tab' && open) {
      close()
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
      focusOption((activeIndex + delta + rows.length) % rows.length)
      return
    }

    if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      focusOption(event.key === 'Home' ? 0 : rows.length - 1)
      return
    }

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      // 여러 명을 이어서 고를 수 있어야 하므로 닫지 않습니다.
      rows[activeIndex]?.choose()
    }
  }

  // 고르는 즉시 라벨이 따라와야 무엇을 고르고 있는지 보입니다. 아직 넘기기 전이라도 초안을 읽습니다.
  const label = coversTeam ? ALL_LABEL : triggerLabel(view, ownMemberId, members)

  return (
    <div className={styles.root} ref={rootRef} onKeyDown={onKeyDown}>
      <button
        ref={triggerRef}
        type="button"
        className={`${styles.trigger} ${open ? styles.isOpen : ''}`}
        aria-label={`보기 범위: ${label}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        onClick={() => (open ? close() : setOpen(true))}
      >
        <span className={styles.triggerLabel}>{label}</span>
        <ChevronDownIcon className={styles.chevron} width={14} height={14} />
      </button>

      {open && (
        <div
          id={listboxId}
          className={styles.menu}
          role="listbox"
          aria-multiselectable="true"
          aria-label="보기 범위"
        >
          {rows.map((row, index) => (
            <button
              key={row.key}
              ref={(node) => {
                optionRefs.current[index] = node
              }}
              type="button"
              role="option"
              aria-selected={row.selected}
              tabIndex={index === activeIndex ? 0 : -1}
              className={`${styles.option} ${index === activeIndex ? styles.isActive : ''} ${row.divided ? styles.isDivided : ''}`}
              onFocus={() => setActiveIndex(index)}
              onPointerMove={() => setActiveIndex(index)}
              onClick={row.choose}
            >
              <CheckIcon
                className={`${styles.check} ${row.selected ? '' : styles.isHidden}`}
                width={14}
                height={14}
              />
              <span>{row.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function triggerLabel(
  scope: Scope,
  ownMemberId: string,
  members: readonly { id: string; display_name: string }[],
): string {
  if (scope.mode === 'all') return ALL_LABEL
  // 본인이 섞여 있으면 앞에 세웁니다. 목록에서 보이는 순서와 맞춥니다.
  const ordered = [...scope.memberIds].sort(
    (a, b) => Number(b === ownMemberId) - Number(a === ownMemberId),
  )
  const names = ordered
    .map((id) =>
      id === ownMemberId ? ME_LABEL : members.find((member) => member.id === id)?.display_name,
    )
    .filter((name): name is string => name !== undefined)
  // 이름을 아직 못 받았으면 인원수로 말합니다. 빈 칸보다는 낫습니다.
  if (names.length === 0) return `${scope.memberIds.length}명`
  return names.length === 1 ? names[0] : `${names[0]} 외 ${names.length - 1}명`
}
