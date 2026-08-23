import {
  useDeferredValue,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import { useNavigate } from 'react-router'
import { createPortal } from 'react-dom'
import DatePicker, { registerLocale } from 'react-datepicker'
import { ko } from 'date-fns/locale'

import { client } from '@/api/client'
import Button from '@/components/Button'
import { errorMessage } from '@/api/errorMessage'
import { ChevronDownIcon, CloseIcon, SearchIcon, TrashIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import { contractCreatePath, orderNewPath, quoteNewPath } from '@/constants/routes'
import type { CalendarEvent, CustomerContactResponse, PageResponse } from '@/types'
import { iso, parseISO } from '@/utils/date'

import {
  DOCUMENT_BY_TASK_STATUS,
  SCHEDULE_STATUSES,
  TASK_GROUPS,
  scheduleStatusLabel,
  type TaskGroup,
} from './statuses'

import 'react-datepicker/dist/react-datepicker.css'
import styles from './EventModal.module.scss'

registerLocale('ko', ko)

interface Props {
  /** 열 때의 일정. 편집은 이 모달 안에서만 하고 저장할 때 한 번에 올립니다. */
  draft: CalendarEvent
  /** 새로 만드는 중이면 지울 것이 아직 없어 삭제를 감춥니다. */
  mode?: 'edit' | 'create'
  onClose: () => void
  onSave: (event: CalendarEvent) => void | Promise<void>
  onDelete?: (id: string) => void | Promise<void>
}

/**
 * 하루의 일은 둘로 갈립니다. 고객을 만나러 가는 '일정' 과, 견적·계약·발주
 * 문서를 밀어 올리는 '업무' 입니다. 필요한 칸도 상태 어휘도 달라, 이 선택이
 * 폼의 절반을 정합니다.
 *
 * 저장할 때는 AgendaKind 로 내려갑니다. 업무는 'internal', 일정은 고른 상태가
 * 정합니다(SCHEDULE_STATUSES).
 */
type EventType = '일정' | '업무'

interface CustomerOption {
  id: string
  name: string
  org: string
  dept: string
  title: string
}

function toCustomerOption(contact: CustomerContactResponse): CustomerOption {
  return {
    id: contact.id,
    name: contact.name,
    org: contact.company_name,
    dept: contact.department ?? '',
    title: contact.job_title ?? '',
  }
}

// 폼은 시작·끝 두 시점으로 다루고, 저장은 '40분' 같은 소요 문구로 합니다.
// 목록·드로어가 그 문구를 그대로 읽으므로 두 표현을 여기서 오갑니다.
const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

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
  const navigate = useNavigate()
  const [form, setForm] = useState<CalendarEvent>(draft)
  const [start, setStart] = useState(() => at(draft.date, draft.time))
  const [end, setEnd] = useState(
    () => new Date(at(draft.date, draft.time).getTime() + parseDur(draft.dur) * MINUTE),
  )
  const [hasEnd, setHasEnd] = useState(draft.endsAt !== null)
  const [type, setType] = useState<EventType>(
    (draft.activityType ?? (draft.kind === 'internal' ? 'task' : 'meeting')) === 'task'
      ? '업무'
      : '일정',
  )
  // 일정 탭 상태. 저장된 값을 화면 이름으로 되돌리고, 없으면 기본값입니다.
  const [scheduleStatus, setScheduleStatus] = useState(() => scheduleStatusLabel(draft.stage))
  // 업무 탭 상태. 서버에 대응하는 값이 없어 늘 빈 채로 시작합니다.
  const [taskGroup, setTaskGroup] = useState<TaskGroup | ''>('')
  const [taskStatus, setTaskStatus] = useState('')
  // 동행자와 미팅대상자도 아직 보낼 곳이 없어 이 모달 안에만 있습니다.
  const [companions, setCompanions] = useState('')
  const [company, setCompany] = useState<CustomerOption | null>(null)
  const [targets, setTargets] = useState<CustomerOption[]>([])

  const [error, setError] = useState('')
  const [customerError, setCustomerError] = useState('')
  const [companyError, setCompanyError] = useState('')
  const [targetError, setTargetError] = useState('')
  const [statusError, setStatusError] = useState('')
  const [rangeError, setRangeError] = useState('')
  const [requestError, setRequestError] = useState('')
  const [pending, setPending] = useState(false)
  // 저장이 끝나면 폼 대신 결과를 보여 줍니다. 닫는 것은 그 화면이 합니다.
  const [saved, setSaved] = useState(false)

  // 종료를 사람이 직접 만졌으면 유형을 바꿔도 그 값을 덮지 않습니다.
  const touchedEnd = useRef(draft.endsAt !== null && mode === 'edit')

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
  //
  // 기본 기간도 함께 바뀝니다. 미팅은 한 시간 남짓이지만 업무는 하루를 잡고
  // 하는 일이라, 아직 종료를 만지지 않았다면 그 길이로 맞춰 둡니다.
  const changeType = (next: EventType) => {
    if (next === type) return
    setType(next)
    setCustomerError('')
    setCompanyError('')
    setTargetError('')
    setStatusError('')
    setRangeError('')

    if (!touchedEnd.current) {
      setEnd(new Date(start.getTime() + (next === '업무' ? DAY : HOUR)))
      setHasEnd(true)
    }

    if (next === '업무') {
      setForm((prev) => ({
        ...prev,
        activityType: 'task',
        kind: 'internal',
        stage: undefined,
        hospital: '',
        dept: '',
        contact: '',
        customerContactId: null,
        customerContactName: '',
        productId: null,
        product: '',
        place: '',
      }))
      setCompanions('')
    } else {
      setForm((prev) => ({ ...prev, activityType: 'meeting', kind: 'visit' }))
      setTaskGroup('')
      setTaskStatus('')
      setCompany(null)
      setTargets([])
    }
  }

  // 갈래를 바꾸면 그 아래 단계는 다른 목록이 됩니다. 남겨 두면 없는 값이 됩니다.
  const changeTaskGroup = (next: TaskGroup | '') => {
    setTaskGroup(next)
    setTaskStatus('')
    setStatusError('')
  }

  // 회사를 바꾸면 그 전 회사 사람들이 대상자로 남아 있으면 안 됩니다.
  const pickCompany = (next: CustomerOption | null) => {
    setCompany(next)
    setTargets([])
    setCompanyError('')
    setTargetError('')
  }

  // 고객을 고르면 회사·부서가 따라옵니다. 직접 입력하지 않는 값들입니다.
  const pickCustomer = (name: string, found?: CustomerOption) => {
    setCustomerError('')
    setForm((prev) => ({
      ...prev,
      contact: found ? [found.name, found.title].filter(Boolean).join(' ') : name,
      hospital: found?.org ?? '',
      dept: found?.dept ?? '',
      customerContactId: found?.id ?? null,
      customerContactName: name,
    }))
  }

  const submit = async () => {
    if (form.title.trim() === '') {
      setError('제목을 입력하세요.')
      return
    }

    if (type === '일정' && form.customerContactName?.trim() && !form.customerContactId) {
      setCustomerError('검색 결과에서 고객을 선택하세요.')
      return
    }

    if (type === '업무') {
      if (taskGroup === '' || taskStatus === '') {
        setStatusError('상태를 선택하세요.')
        return
      }
      if (!company) {
        setCompanyError('고객사를 선택하세요.')
        return
      }
      if (targets.length === 0) {
        setTargetError('미팅대상자를 선택하세요.')
        return
      }
    }

    // 소요는 시작과 끝의 차이입니다. 목록·드로어는 이 문구만 읽습니다.
    const minutes = Math.round((end.getTime() - start.getTime()) / MINUTE)
    if (hasEnd && minutes <= 0) {
      setRangeError('종료가 시작보다 빠릅니다.')
      return
    }

    // 화면에서 고른 상태를 저장이 아는 값으로 옮겨 적습니다. 업무 쪽 단계는
    // 아직 서버에 자리가 없어 태그 없이, 사내 일로 내려갑니다.
    const picked = SCHEDULE_STATUSES.find((s) => s.label === scheduleStatus)

    setPending(true)
    setRequestError('')
    try {
      await onSave({
        ...form,
        title: form.title.trim(),
        date: iso(start),
        time: hhmm(start),
        dur: form.allDay ? '종일' : hasEnd ? durLabel(minutes) : '',
        allDay: form.allDay ?? false,
        stage: type === '일정' ? picked?.stage : undefined,
        kind: type === '일정' ? (picked?.kind ?? 'visit') : 'internal',
      })
      if (mode === 'create') setSaved(true)
      else onClose()
    } catch {
      setRequestError(
        mode === 'create' ? '일정을 등록하지 못했습니다.' : '일정을 수정하지 못했습니다.',
      )
    } finally {
      setPending(false)
    }
  }

  // 등록한 단계가 곧 쓸 문서를 가리키면(견적작성·초안작성·발주 접수) 이어서
  // 그 작성 화면까지 열어 줍니다.
  const docName = type === '업무' ? DOCUMENT_BY_TASK_STATUS[taskStatus] : undefined

  const goToDocument = () => {
    onClose()
    if (docName === '견적서') navigate(quoteNewPath())
    else if (docName === '계약서') navigate(contractCreatePath())
    else if (docName === '발주') navigate(orderNewPath())
  }

  const remove = async () => {
    if (!onDelete) return
    setPending(true)
    setRequestError('')
    try {
      await onDelete(form.id)
    } catch {
      setRequestError('일정을 삭제하지 못했습니다.')
    } finally {
      setPending(false)
    }
  }

  // 등록을 마친 뒤. 문서로 이어질 단계면 그리로 갈지 묻고, 아니면 알리고 닫습니다.
  if (saved) {
    return (
      <Modal
        title="일정 등록"
        onClose={onClose}
        footer={
          docName ? (
            <>
              <Button type="button" variant="outline" onClick={onClose}>
                취소
              </Button>
              <Button type="button" onClick={goToDocument}>
                이동
              </Button>
            </>
          ) : (
            <Button type="button" onClick={onClose}>
              확인
            </Button>
          )
        }
      >
        <div className={styles.saved}>
          <p>등록되었습니다.</p>
          {docName && <p>{docName} 작성 화면으로 이동하시겠습니까?</p>}
        </div>
      </Modal>
    )
  }

  return (
    <Modal
      title={mode === 'create' ? '일정 등록' : '일정 수정'}
      onClose={() => !pending && onClose()}
      onSubmit={submit}
      footer={
        <>
          {onDelete && mode === 'edit' && (
            <Button
              type="button"
              variant="ghost"
              className={styles.delete}
              disabled={pending}
              onClick={() => void remove()}
            >
              <TrashIcon width={15} height={15} />
              삭제
            </Button>
          )}
          <Button type="button" variant="outline" disabled={pending} onClick={onClose}>
            취소
          </Button>
          <Button type="submit" disabled={pending}>
            {pending ? '저장 중…' : '저장'}
          </Button>
        </>
      }
    >
      <div className={styles.grid}>
        {/* 태그 두 개가 무엇을 고르는 자리인지 스스로 말하므로 라벨을 붙이지
            않습니다. 스크린리더는 radiogroup 의 이름으로 같은 것을 듣습니다. */}
        <div className={`${styles.field} ${styles.isWide}`}>
          <div className={styles.typeToggle} role="radiogroup" aria-label="일정 유형">
            {(['일정', '업무'] as const).map((t) => (
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
            날짜<b aria-hidden="true">*</b>
          </span>
          <div className={styles.range}>
            <Picker selected={start} onChange={moveStart} label="시작" />
            <Picker
              selected={end}
              onChange={(date) => {
                if (!date) return
                setEnd(date)
                setHasEnd(true)
                touchedEnd.current = true
              }}
              label="종료"
              minDate={start}
            />
          </div>
          {rangeError && <span className={styles.error}>{rangeError}</span>}
        </div>

        {type === '일정' ? (
          <>
            <Field label="상태" required>
              <select value={scheduleStatus} onChange={(e) => setScheduleStatus(e.target.value)}>
                {SCHEDULE_STATUSES.map((s) => (
                  <option key={s.label} value={s.label}>
                    {s.label}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="장소">
              <input
                value={form.place ?? ''}
                placeholder="미팅 장소"
                onChange={(e) => set('place', e.target.value)}
              />
            </Field>

            <div className={`${styles.field} ${styles.isWide}`}>
              <span className={styles.label}>고객</span>
              <CustomerPicker
                value={form.customerContactName ?? form.contact ?? ''}
                selectedId={form.customerContactId ?? null}
                tag={form.hospital ? `${form.hospital}${form.dept ? ` · ${form.dept}` : ''}` : ''}
                error={customerError}
                onChange={pickCustomer}
              />
            </div>

            <Field label="동행자" wide>
              <input
                value={companions}
                placeholder="함께 가는 사람 (예: 홍길동, 김대리)"
                onChange={(e) => setCompanions(e.target.value)}
              />
            </Field>
          </>
        ) : (
          <>
            {/* 갈래를 먼저 고르면 그 안의 단계만 남습니다. 서른 개 가까운 단계를
                한 줄에 펴 놓으면 어느 갈래의 것인지 읽어 내야 합니다. */}
            <div className={`${styles.field} ${styles.isWide}`}>
              <span className={styles.label}>
                상태<b aria-hidden="true">*</b>
              </span>
              <div className={styles.statusPair}>
                <select
                  aria-label="업무 구분"
                  value={taskGroup}
                  onChange={(e) => changeTaskGroup(e.target.value as TaskGroup | '')}
                >
                  <option value="">선택하세요</option>
                  {TASK_GROUPS.map(({ group }) => (
                    <option key={group} value={group}>
                      {group}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="업무 상태"
                  value={taskStatus}
                  disabled={taskGroup === ''}
                  onChange={(e) => {
                    setTaskStatus(e.target.value)
                    setStatusError('')
                  }}
                >
                  <option value="">
                    {taskGroup === '' ? '구분을 먼저 고르세요' : '선택하세요'}
                  </option>
                  {TASK_GROUPS.find(({ group }) => group === taskGroup)?.items.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </div>
              {statusError && <span className={styles.error}>{statusError}</span>}
            </div>

            <div className={`${styles.field} ${styles.isWide}`}>
              <span className={styles.label}>
                고객사<b aria-hidden="true">*</b>
              </span>
              <CompanyPicker value={company} error={companyError} onChange={pickCompany} />
            </div>

            <div className={`${styles.field} ${styles.isWide}`}>
              <span className={styles.label}>
                미팅대상자<b aria-hidden="true">*</b>
              </span>
              <TargetPicker
                company={company}
                picked={targets}
                error={targetError}
                onChange={(next) => {
                  setTargets(next)
                  setTargetError('')
                }}
              />
            </div>
          </>
        )}

        <Field label="메모" wide>
          <textarea
            rows={3}
            value={form.brief ?? ''}
            placeholder={type === '일정' ? '이번 미팅에서 확인할 것' : '이 업무에서 다룰 것'}
            onChange={(e) => set('brief', e.target.value)}
          />
        </Field>

        {requestError && (
          <p className={`${styles.error} ${styles.isWide}`} role="alert">
            {requestError}
          </p>
        )}
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

/**
 * 고객 검색 한 번. 고객·고객사·미팅대상자 세 칸이 같은 목록을 다르게 추릴 뿐이라
 * 불러오는 일은 여기 한 곳에 둡니다. 닫혀 있는 동안에는 부르지 않습니다.
 */
function useContactSearch(query: string, open: boolean) {
  const [matches, setMatches] = useState<CustomerOption[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const deferredQuery = useDeferredValue(query.trim())

  useEffect(() => {
    if (!open) return
    const controller = new AbortController()

    setLoading(true)
    setLoadError(null)
    void client
      .get<PageResponse<CustomerContactResponse>>('/customer-contacts', {
        params: {
          q: deferredQuery === '' ? undefined : deferredQuery.slice(0, 100),
          skip: 0,
          limit: MAX_MATCHES,
        },
        signal: controller.signal,
      })
      .then(({ data }) => {
        if (!controller.signal.aborted) setMatches(data.items.map(toCustomerOption))
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return
        setMatches([])
        setLoadError(errorMessage(reason, '고객 검색 결과를 불러오지 못했습니다.'))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [deferredQuery, open, reloadKey])

  return { matches, loading, loadError, reload: () => setReloadKey((value) => value + 1) }
}

// 모달 본문은 overflow: auto, 다이얼로그는 overflow: hidden 이라 목록을 흐름
// 안에 두면 잘려 보이지 않습니다. 달력 팝업처럼 body 로 꺼내 화면 좌표에 띄웁니다.
// ponytail: 좌표는 열 때 한 번만 잽니다. 열어 둔 채 본문을 스크롤하면
// 목록이 제자리에 남습니다. 거슬리면 scroll 에서 닫으면 됩니다.
function menuPosition(box: HTMLDivElement | null) {
  const rect = box?.getBoundingClientRect()
  if (!rect) return undefined
  const roomBelow = window.innerHeight - rect.bottom
  return {
    left: rect.left,
    width: rect.width,
    ...(roomBelow < 200 ? { bottom: window.innerHeight - rect.top + 4 } : { top: rect.bottom + 4 }),
  }
}

/** 세 검색칸이 함께 쓰는 결과 목록. 비어 있음·불러오는 중·실패를 여기서 답니다. */
function PickerMenu({
  id,
  label,
  style,
  loading,
  loadError,
  onRetry,
  children,
  empty,
}: {
  id: string
  label: string
  style?: React.CSSProperties
  loading: boolean
  loadError: string | null
  onRetry: () => void
  children: ReactNode
  empty: boolean
}) {
  return createPortal(
    <div id={id} className={styles.menu} style={style} role="listbox" aria-label={label}>
      {loading && (
        <p className={styles.option} role="status">
          고객을 불러오는 중입니다.
        </p>
      )}
      {!loading && loadError && (
        <div className={styles.option} role="alert">
          <span>{loadError}</span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onMouseDown={(event) => event.preventDefault()}
            onClick={onRetry}
          >
            다시 시도
          </Button>
        </div>
      )}
      {!loading && !loadError && empty && <p className={styles.option}>검색 결과가 없습니다.</p>}
      {!loading && !loadError && children}
    </div>,
    document.body,
  )
}

function CustomerPicker({
  value,
  selectedId,
  tag,
  error,
  onChange,
}: {
  value: string
  selectedId: string | null
  tag: string
  error: string
  onChange: (name: string, found?: CustomerOption) => void
}) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)
  const listboxId = `customers-${useId().replaceAll(':', '')}`
  const errorId = `${listboxId}-error`

  const { matches, loading, loadError, reload } = useContactSearch(value, open)

  useEffect(() => setActive(0), [matches])

  const choose = (c: CustomerOption) => {
    onChange(c.name, c)
    setOpen(false)
  }

  const menuStyle = open ? menuPosition(boxRef.current) : undefined

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
      if (matches.length === 0) return
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
          aria-controls={open && matches.length > 0 ? listboxId : undefined}
          aria-activedescendant={
            open && matches[active] ? `${listboxId}-${matches[active].id}` : undefined
          }
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
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

      {error && (
        <span id={errorId} className={styles.error} role="alert">
          {error}
        </span>
      )}

      {open && (
        <PickerMenu
          id={listboxId}
          label="고객"
          style={menuStyle}
          loading={loading}
          loadError={loadError}
          onRetry={reload}
          empty={matches.length === 0}
        >
          {matches.map((c, i) => (
            <button
              key={c.id}
              id={`${listboxId}-${c.id}`}
              type="button"
              role="option"
              aria-selected={c.id === selectedId}
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
        </PickerMenu>
      )}
    </div>
  )
}

/**
 * 고객사 검색. 고객 목록에서 회사 이름만 추려 보여 줍니다. 같은 회사 사람이
 * 여럿이라 이름이 겹치므로 회사 이름 하나로 접습니다.
 */
function CompanyPicker({
  value,
  error,
  onChange,
}: {
  value: CustomerOption | null
  error: string
  onChange: (next: CustomerOption | null) => void
}) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [query, setQuery] = useState(value?.org ?? '')
  const boxRef = useRef<HTMLDivElement>(null)
  const listboxId = `companies-${useId().replaceAll(':', '')}`
  const errorId = `${listboxId}-error`

  const { matches, loading, loadError, reload } = useContactSearch(query, open)

  // 한 회사에 여러 명이 있으면 목록에 회사가 여러 줄로 나옵니다. 첫 사람만 남깁니다.
  const companies = useMemo(() => {
    const seen = new Set<string>()
    return matches.filter((c) => {
      if (c.org === '' || seen.has(c.org)) return false
      seen.add(c.org)
      return true
    })
  }, [matches])

  useEffect(() => setActive(0), [companies])

  const choose = (c: CustomerOption) => {
    setQuery(c.org)
    onChange(c)
    setOpen(false)
  }

  const menuStyle = open ? menuPosition(boxRef.current) : undefined

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape' && open) {
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
      if (companies.length === 0) return
      const delta = e.key === 'ArrowDown' ? 1 : -1
      setActive((prev) => (prev + delta + companies.length) % companies.length)
      return
    }

    if (e.key === 'Enter' && open && companies[active]) {
      e.preventDefault()
      choose(companies[active])
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
          value={query}
          placeholder="회사명으로 검색"
          aria-label="고객사"
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          aria-controls={open && companies.length > 0 ? listboxId : undefined}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          autoComplete="off"
          onChange={(e) => {
            setQuery(e.target.value)
            // 이름을 고쳐 쓰기 시작하면 앞서 고른 회사는 더 이상 그 값이 아닙니다.
            if (value) onChange(null)
            setActive(0)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
        />
        <button
          type="button"
          className={`${styles.toggle} ${open ? styles.isOpen : ''}`}
          aria-label={open ? '고객사 목록 닫기' : '고객사 목록 열기'}
          tabIndex={-1}
          onClick={() => setOpen((prev) => !prev)}
        >
          <ChevronDownIcon width={16} height={16} />
        </button>
      </div>

      {error && (
        <span id={errorId} className={styles.error} role="alert">
          {error}
        </span>
      )}

      {open && (
        <PickerMenu
          id={listboxId}
          label="고객사"
          style={menuStyle}
          loading={loading}
          loadError={loadError}
          onRetry={reload}
          empty={companies.length === 0}
        >
          {companies.map((c, i) => (
            <button
              key={c.org}
              type="button"
              role="option"
              aria-selected={c.org === value?.org}
              className={`${styles.option} ${i === active ? styles.isActive : ''}`}
              onPointerMove={() => setActive(i)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(c)}
            >
              <b>{c.org}</b>
            </button>
          ))}
        </PickerMenu>
      )}
    </div>
  )
}

/**
 * 미팅대상자. 고른 고객사 소속인 사람만 보여 주고 여럿을 담습니다.
 * 담은 사람은 칩으로 남아, 목록을 다시 열지 않고도 누구를 골랐는지 보입니다.
 */
function TargetPicker({
  company,
  picked,
  error,
  onChange,
}: {
  company: CustomerOption | null
  picked: CustomerOption[]
  error: string
  onChange: (next: CustomerOption[]) => void
}) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [query, setQuery] = useState('')
  const boxRef = useRef<HTMLDivElement>(null)
  const listboxId = `targets-${useId().replaceAll(':', '')}`
  const errorId = `${listboxId}-error`

  // 아무것도 치지 않았으면 회사 이름으로 그 회사 사람들을 부릅니다.
  const search = query.trim() === '' ? (company?.org ?? '') : query
  const { matches, loading, loadError, reload } = useContactSearch(search, open && company !== null)

  // 다른 회사 사람과 이미 담은 사람은 목록에서 뺍니다.
  const candidates = useMemo(() => {
    if (!company) return []
    const taken = new Set(picked.map((p) => p.id))
    return matches.filter((c) => c.org === company.org && !taken.has(c.id))
  }, [matches, company, picked])

  useEffect(() => setActive(0), [candidates])

  const add = (c: CustomerOption) => {
    onChange([...picked, c])
    setQuery('')
  }

  const menuStyle = open && company ? menuPosition(boxRef.current) : undefined

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape' && open) {
      e.stopPropagation()
      setOpen(false)
      return
    }

    // 빈 칸에서 지우면 마지막으로 담은 사람을 뺍니다. 칩 UI 의 관례입니다.
    if (e.key === 'Backspace' && query === '' && picked.length > 0) {
      onChange(picked.slice(0, -1))
      return
    }

    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (!open) {
        setOpen(true)
        return
      }
      if (candidates.length === 0) return
      const delta = e.key === 'ArrowDown' ? 1 : -1
      setActive((prev) => (prev + delta + candidates.length) % candidates.length)
      return
    }

    if (e.key === 'Enter' && open && candidates[active]) {
      e.preventDefault()
      add(candidates[active])
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
      <div className={`${styles.customerBox} ${styles.hasChips}`} ref={boxRef}>
        <SearchIcon width={16} height={16} />
        <div className={styles.chips}>
          {picked.map((p) => (
            <span key={p.id} className={styles.chip}>
              {p.name}
              {p.title && ` ${p.title}`}
              <button
                type="button"
                className={styles.chipRemove}
                aria-label={`${p.name} 빼기`}
                onClick={() => onChange(picked.filter((c) => c.id !== p.id))}
              >
                <CloseIcon width={12} height={12} />
              </button>
            </span>
          ))}
          <input
            value={query}
            placeholder={company ? '이름으로 검색' : '고객사를 먼저 고르세요'}
            aria-label="미팅대상자"
            role="combobox"
            aria-expanded={open}
            aria-autocomplete="list"
            aria-controls={open && candidates.length > 0 ? listboxId : undefined}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? errorId : undefined}
            autoComplete="off"
            disabled={!company}
            onChange={(e) => {
              setQuery(e.target.value)
              setActive(0)
              setOpen(true)
            }}
            onFocus={() => setOpen(true)}
          />
        </div>
      </div>

      {error && (
        <span id={errorId} className={styles.error} role="alert">
          {error}
        </span>
      )}

      {open && company && (
        <PickerMenu
          id={listboxId}
          label="미팅대상자"
          style={menuStyle}
          loading={loading}
          loadError={loadError}
          onRetry={reload}
          empty={candidates.length === 0}
        >
          {candidates.map((c, i) => (
            <button
              key={c.id}
              type="button"
              role="option"
              aria-selected={false}
              className={`${styles.option} ${i === active ? styles.isActive : ''}`}
              onPointerMove={() => setActive(i)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => add(c)}
            >
              <b>{c.name}</b>
              <span>
                {c.dept}
                {c.title && ` · ${c.title}`}
              </span>
            </button>
          ))}
        </PickerMenu>
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
