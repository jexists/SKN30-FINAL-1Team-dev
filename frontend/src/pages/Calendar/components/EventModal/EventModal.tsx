import { useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import DatePicker, { registerLocale } from 'react-datepicker'
import { ko } from 'date-fns/locale'

import Button from '@/components/Button'
import { ChevronDownIcon, SearchIcon, TrashIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import { EXTERNAL_STATUSES, INTERNAL_STATUSES } from '@/shared/agenda'
import { customers } from '@/shared/customers'
import type { CalendarEvent, Customer, ScheduleStatus } from '@/types'
import { iso, parseISO } from '@/utils/date'

import 'react-datepicker/dist/react-datepicker.css'
import styles from './EventModal.module.scss'

registerLocale('ko', ko)

interface Props {
  /** 열 때의 일정. 편집은 이 모달 안에서만 하고 저장할 때 한 번에 올립니다. */
  draft: CalendarEvent
  /** 새로 만드는 중이면 지울 것이 아직 없어 삭제를 감춥니다. */
  mode?: 'edit' | 'create'
  onClose: () => void
  onSave: (event: CalendarEvent) => void
  onDelete?: (id: string) => void
}

/**
 * 일정은 고객을 만나러 가는 것과 사내에서 처리하는 것 둘로 갈립니다.
 * 고객·상태는 앞의 것에만 있으므로 이 선택이 폼의 절반을 정합니다.
 *
 * 저장할 때는 AgendaKind 로 내려갑니다. 사내 일은 'internal', 나머지는 방문입니다.
 */
type EventType = '미팅' | '업무'

/**
 * 상태 목록. 외부·내부를 나누어 보여주지 않고 한 줄로 폅니다.
 * 고르는 사람에게 그 구분은 일정을 적을 때 생각할 거리가 아닙니다.
 * (태그 색은 저장된 값을 보고 statusScope 가 알아서 가릅니다.)
 */
const STATUSES: readonly ScheduleStatus[] = [...EXTERNAL_STATUSES, ...INTERNAL_STATUSES]

// 폼은 시작·끝 두 시점으로 다루고, 저장은 '40분' 같은 소요 문구로 합니다.
// 목록·드로어가 그 문구를 그대로 읽으므로 두 표현을 여기서 오갑니다.
const MINUTE = 60_000

function at(date: string, time: string): Date {
  const [h, m] = time.split(':').map(Number)
  return new Date(parseISO(date).getTime() + (h * 60 + m) * MINUTE)
}

function hhmm(d: Date): string {
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** '1시간 30분' → 90. 못 읽으면 60 으로 둡니다. */
function parseDur(dur: string): number {
  const hours = /(\d+)\s*시간/.exec(dur)
  const mins = /(\d+)\s*분/.exec(dur)
  const total = (hours ? Number(hours[1]) * 60 : 0) + (mins ? Number(mins[1]) : 0)
  return total > 0 ? total : 60
}

function durLabel(minutes: number): string {
  if (minutes <= 0) return '0분'
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (h === 0) return `${m}분`
  return m === 0 ? `${h}시간` : `${h}시간 ${m}분`
}

export default function EventModal({ draft, mode = 'edit', onClose, onSave, onDelete }: Props) {
  const [form, setForm] = useState<CalendarEvent>(draft)
  const [start, setStart] = useState(() => at(draft.date, draft.time))
  const [end, setEnd] = useState(
    () => new Date(at(draft.date, draft.time).getTime() + parseDur(draft.dur) * MINUTE),
  )
  const [type, setType] = useState<EventType>(draft.kind === 'internal' ? '업무' : '미팅')
  const [error, setError] = useState('')
  const [rangeError, setRangeError] = useState('')

  const set = <K extends keyof CalendarEvent>(key: K, value: CalendarEvent[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  // 시작을 옮기면 끝도 같은 만큼 따라갑니다. 30분짜리 일정을 다음 날로 미룰 때
  // 끝을 다시 고르게 하지 않기 위함입니다.
  const moveStart = (next: Date | null) => {
    if (!next) return
    const shift = next.getTime() - start.getTime()
    setStart(next)
    setEnd((prev) => new Date(prev.getTime() + shift))
  }

  // 유형을 바꾸면 반대쪽에만 있는 칸이 남지 않게 비웁니다. 저장 직전에 거르면
  // 화면에는 사라졌는데 값은 살아 있는 상태가 생겨 여기서 함께 정리합니다.
  const changeType = (next: EventType) => {
    setType(next)
    if (next === '업무') {
      setForm((prev) => ({
        ...prev,
        kind: 'internal',
        stage: undefined,
        hospital: '',
        dept: '',
        contact: '',
      }))
    } else {
      setForm((prev) => ({ ...prev, kind: 'visit' }))
    }
  }

  // 고객을 고르면 회사·부서가 따라옵니다. 직접 입력하지 않는 값들입니다.
  const pickCustomer = (name: string, found?: Customer) => {
    const match = found ?? customers.find((c) => c.name === name)
    setForm((prev) => ({
      ...prev,
      contact: name,
      hospital: match?.org ?? '',
      dept: match?.dept ?? '',
    }))
  }

  const submit = () => {
    if (form.title.trim() === '') {
      setError('제목을 입력하세요.')
      return
    }

    // 소요는 시작과 끝의 차이입니다. 목록·드로어는 이 문구만 읽습니다.
    const minutes = Math.round((end.getTime() - start.getTime()) / MINUTE)
    if (minutes <= 0) {
      setRangeError('종료가 시작보다 빠릅니다.')
      return
    }

    onSave({
      ...form,
      title: form.title.trim(),
      date: iso(start),
      time: hhmm(start),
      dur: durLabel(minutes),
    })
  }

  return (
    <Modal
      title={mode === 'create' ? '일정 등록' : '일정 수정'}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          {onDelete && mode === 'edit' && (
            <Button
              type="button"
              variant="ghost"
              className={styles.delete}
              onClick={() => onDelete(form.id)}
            >
              <TrashIcon width={15} height={15} />
              삭제
            </Button>
          )}
          <Button type="button" variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button type="submit">저장</Button>
        </>
      }
    >
      <div className={styles.grid}>
        {/* 태그 두 개가 무엇을 고르는 자리인지 스스로 말하므로 라벨을 붙이지
            않습니다. 스크린리더는 radiogroup 의 이름으로 같은 것을 듣습니다. */}
        <div className={`${styles.field} ${styles.isWide}`}>
          <div className={styles.typeToggle} role="radiogroup" aria-label="일정 유형">
            {(['미팅', '업무'] as const).map((t) => (
              <button
                key={t}
                type="button"
                role="radio"
                aria-checked={type === t}
                className={`${styles.typeBtn} ${type === t ? styles.isOn : ''}`}
                onClick={() => changeType(t)}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <Field label="제목" required error={error} wide>
          <input
            value={form.title}
            placeholder="제목을 입력하세요."
            onChange={(e) => set('title', e.target.value)}
          />
        </Field>

        <div className={`${styles.field} ${styles.isWide}`}>
          <span className={styles.label}>
            일정<b aria-hidden="true">*</b>
          </span>
          <div className={styles.range}>
            <Picker selected={start} onChange={moveStart} label="시작" />
            <Picker selected={end} onChange={(d) => d && setEnd(d)} label="종료" minDate={start} />
          </div>
          {rangeError && <span className={styles.error}>{rangeError}</span>}
        </div>

        {type === '미팅' && (
          <Field label="상태">
            <select
              value={form.stage ?? ''}
              onChange={(e) =>
                set('stage', (e.target.value || undefined) as CalendarEvent['stage'])
              }
            >
              <option value="">선택 안 함</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
        )}

        <Field label="장소" wide={type === '업무'}>
          <input
            value={form.place ?? ''}
            placeholder="미팅 장소"
            onChange={(e) => set('place', e.target.value)}
          />
        </Field>

        {type === '미팅' && (
          <div className={`${styles.field} ${styles.isWide}`}>
            <span className={styles.label}>고객</span>
            <CustomerPicker
              value={form.contact ?? ''}
              tag={form.hospital ? `${form.hospital}${form.dept ? ` · ${form.dept}` : ''}` : ''}
              onChange={pickCustomer}
            />
          </div>
        )}

        <Field label="메모" wide>
          <textarea
            rows={3}
            value={form.brief ?? ''}
            placeholder={type === '미팅' ? '이번 미팅에서 확인할 것' : '이 업무에서 다룰 것'}
            onChange={(e) => set('brief', e.target.value)}
          />
        </Field>
      </div>
    </Modal>
  )
}

/**
 * 날짜와 시각을 한 칸에서 받습니다. 네이티브 date/time 입력은 브라우저가 최소
 * 폭을 정해 버려 520px 모달 안에서 잘렸습니다. 여기서는 표시 형식을 우리가
 * 정하므로 좁은 칸에도 온전히 들어갑니다.
 */
function Picker({
  selected,
  onChange,
  label,
  minDate,
}: {
  selected: Date
  onChange: (date: Date | null) => void
  label: string
  minDate?: Date
}) {
  // 열린 달력은 DatePicker 의 형제로 붙습니다. 이 감싸개가 없으면 그 달력이
  // 기간 그리드의 칸 하나를 차지해 종료 입력을 다음 줄로 밀어냅니다.
  return (
    <div className={styles.pickerCell}>
      <DatePicker
        selected={selected}
        onChange={onChange}
        minDate={minDate}
        showTimeSelect
        timeIntervals={10}
        timeCaption="시각"
        locale="ko"
        dateFormat="M월 d일 (EEE) a h:mm"
        // date-fns 의 ko 로케일은 달 제목을 '8월 2026' 으로 냅니다. 우리말 차례로 뒤집습니다.
        dateFormatCalendar="yyyy년 M월"
        customInput={<input aria-label={label} className={styles.picker} />}
        popperPlacement="bottom-start"
        // 모달이 overflow: hidden 이라, 아래쪽에서 열린 달력이 잘리지 않게 띄웁니다.
        popperProps={{ strategy: 'fixed' }}
      />
    </div>
  )
}

/**
 * 고객 검색. 네이티브 datalist 는 목록을 브라우저가 그려 앱과 다른 모양으로
 * 뜨고 회사 이름도 함께 보여주지 못해, 같은 토큰으로 칠한 콤보박스로 답니다.
 * 회사·부서는 고른 뒤 딸려 오는 값이라 입력칸을 따로 두지 않고 태그로 붙입니다.
 */
const MAX_MATCHES = 8

function CustomerPicker({
  value,
  tag,
  onChange,
}: {
  value: string
  tag: string
  onChange: (name: string, found?: Customer) => void
}) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)

  // 빈 칸이면 이름 순 앞부분을 그대로 보여 줍니다. 무엇을 칠 수 있는지
  // 한 번 훑고 고르는 쪽이 빈 목록을 마주하는 것보다 빠릅니다.
  const query = value.trim()
  const matches = customers
    .filter((c) => query === '' || c.name.includes(query) || c.org.includes(query))
    .slice(0, MAX_MATCHES)

  const choose = (c: Customer) => {
    onChange(c.name, c)
    setOpen(false)
  }

  // 모달 본문은 overflow: auto, 다이얼로그는 overflow: hidden 이라 목록을 흐름
  // 안에 두면 잘려 보이지 않습니다. 달력 팝업처럼 body 로 꺼내 화면 좌표에 띄웁니다.
  // ponytail: 좌표는 열 때 한 번만 잽니다. 열어 둔 채 본문을 스크롤하면
  // 목록이 제자리에 남습니다. 거슬리면 scroll 에서 닫으면 됩니다.
  const rect = open ? boxRef.current?.getBoundingClientRect() : undefined
  const roomBelow = rect ? window.innerHeight - rect.bottom : 0
  const menuStyle = rect
    ? {
        left: rect.left,
        width: rect.width,
        ...(roomBelow < 200
          ? { bottom: window.innerHeight - rect.top + 4 }
          : { top: rect.bottom + 4 }),
      }
    : undefined

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape' && open) {
      // 모달까지 올라가면 일정 편집이 통째로 닫힙니다. 목록만 닫습니다.
      e.stopPropagation()
      setOpen(false)
      return
    }

    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (!open) {
        setOpen(true)
        return
      }
      const delta = e.key === 'ArrowDown' ? 1 : -1
      setActive((prev) => (prev + delta + matches.length) % matches.length)
      return
    }

    if (e.key === 'Enter' && open && matches[active]) {
      e.preventDefault()
      choose(matches[active])
    }
  }

  return (
    <div
      className={styles.customer}
      onKeyDown={onKeyDown}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false)
      }}
    >
      <div className={styles.customerBox} ref={boxRef}>
        <SearchIcon width={16} height={16} />
        <input
          value={value}
          placeholder="이름으로 검색"
          aria-label="고객"
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          autoComplete="off"
          onChange={(e) => {
            onChange(e.target.value)
            setActive(0)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
        />
        {tag && <span className={styles.pickedTag}>{tag}</span>}
        <button
          type="button"
          className={`${styles.toggle} ${open ? styles.isOpen : ''}`}
          aria-label={open ? '고객 목록 닫기' : '고객 목록 열기'}
          tabIndex={-1}
          onClick={() => setOpen((prev) => !prev)}
        >
          <ChevronDownIcon width={16} height={16} />
        </button>
      </div>

      {open &&
        matches.length > 0 &&
        createPortal(
          <div className={styles.menu} style={menuStyle} role="listbox" aria-label="고객">
            {matches.map((c, i) => (
              <button
                key={c.id}
                type="button"
                role="option"
                aria-selected={c.name === value}
                className={`${styles.option} ${i === active ? styles.isActive : ''}`}
                onPointerMove={() => setActive(i)}
                // 목록은 입력칸 밖(body)에 있어, 누르는 순간 포커스가 빠지면
                // 클릭이 닿기 전에 닫힙니다. 포커스를 입력에 붙들어 둡니다.
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => choose(c)}
              >
                <b>{c.name}</b>
                <span>
                  {c.org}
                  {c.dept && ` · ${c.dept}`}
                </span>
              </button>
            ))}
          </div>,
          document.body,
        )}
    </div>
  )
}

interface FieldProps {
  label: string
  required?: boolean
  error?: string
  wide?: boolean
  children: ReactNode
}

function Field({ label, required, error, wide, children }: FieldProps) {
  return (
    <label className={`${styles.field} ${wide ? styles.isWide : ''}`}>
      <span className={styles.label}>
        {label}
        {required && <b aria-hidden="true">*</b>}
      </span>
      {children}
      {error && <span className={styles.error}>{error}</span>}
    </label>
  )
}
