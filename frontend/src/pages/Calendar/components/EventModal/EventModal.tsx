import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router'
import DatePicker, { registerLocale } from 'react-datepicker'
import { ko } from 'date-fns/locale'

import { client } from '@/api/client'
import Button from '@/components/Button'
import CompanyAutocomplete, { type CompanySelection } from '@/components/CompanyAutocomplete'
import ContactPicker, { toContactOption, type ContactOption } from '@/components/ContactPicker'
import { TrashIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import { contractCreatePath, orderNewPath, quoteNewPath } from '@/constants/routes'
import CustomerFormModal from '@/pages/Customers/components/CustomerFormModal'
import { showToast } from '@/shared/toast'
import type { CalendarEvent, CustomerCompanyResponse, CustomerContactResponse } from '@/types'
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

/** 고객사 칸이 들고 있는 회사의 id. 직접 등록은 쓰지 않아 늘 이미 있는 회사입니다. */
function companyId(selection: CompanySelection | null): string | null {
  return selection?.kind === 'existing' ? selection.company.id : null
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
  // 고객사는 두 탭이 함께 씁니다. 일정 탭은 그 아래에서 한 명, 업무 탭은 여럿을 고릅니다.
  const [company, setCompany] = useState<CompanySelection | null>(null)
  const [customer, setCustomer] = useState<ContactOption | null>(null)
  const [targets, setTargets] = useState<ContactOption[]>([])
  // 아직 없는 고객사·고객은 이 자리에서 등록합니다. null 이면 등록 모달이 닫힌 상태입니다.
  const [creating, setCreating] = useState<{
    company: CompanySelection | null
    name: string
  } | null>(null)

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

  // 고쳐 쓰려고 연 일정. 저장된 것은 고객 id 하나뿐이라 회사·담당자 두 칸을 채우려면
  // 그 고객을 한 번 읽어야 합니다. 실패하면 두 칸을 빈 채로 두고 다시 고르게 합니다.
  const savedContactId = draft.customerContactId ?? null
  useEffect(() => {
    if (savedContactId === null) return
    const controller = new AbortController()

    void client
      .get<CustomerContactResponse>(`/customer-contacts/${savedContactId}`, {
        signal: controller.signal,
      })
      .then(async ({ data }) => {
        const { data: found } = await client.get<CustomerCompanyResponse>(
          `/customer-companies/${data.company_id}`,
          { signal: controller.signal },
        )
        if (controller.signal.aborted) return
        setCompany({ kind: 'existing', company: found })
        setCustomer(toContactOption(data))
      })
      .catch(() => {})

    return () => controller.abort()
  }, [savedContactId])

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

    // 고객사는 두 탭이 함께 쓰므로 유형을 바꿔도 남깁니다. 그 아래에서 고른 사람만
    // 반대쪽 칸의 것이라 비웁니다.
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
      setCustomer(null)
    } else {
      setForm((prev) => ({ ...prev, activityType: 'meeting', kind: 'visit' }))
      setTaskGroup('')
      setTaskStatus('')
      setTargets([])
    }
  }

  // 갈래를 바꾸면 그 아래 단계는 다른 목록이 됩니다. 남겨 두면 없는 값이 됩니다.
  const changeTaskGroup = (next: TaskGroup | '') => {
    setTaskGroup(next)
    setTaskStatus('')
    setStatusError('')
  }

  // 고객을 고르면 회사·부서가 따라옵니다. 직접 입력하지 않는 값들입니다.
  const pickCustomer = (found: ContactOption | null) => {
    setCustomer(found)
    setCustomerError('')
    setForm((prev) => ({
      ...prev,
      contact: found ? [found.name, found.title].filter(Boolean).join(' ') : '',
      hospital: found?.org ?? '',
      dept: found?.dept ?? '',
      customerContactId: found?.id ?? null,
      customerContactName: found?.name ?? '',
    }))
  }

  // 회사를 바꾸면 그 전 회사 사람들이 고객·대상자로 남아 있으면 안 됩니다.
  const pickCompany = (next: CompanySelection | null) => {
    // 아직 없는 회사를 고른 것은 "여기 없으니 새로 만들겠다" 는 뜻입니다. 일정에 붙는 것은
    // 회사가 아니라 그 회사의 고객이라, 회사만 만들어 두면 일정에는 아무것도 남지 않습니다.
    // 그래서 곧바로 고객 등록으로 넘겨 회사와 사람을 한 번에 만듭니다.
    if (next?.kind === 'new') {
      setCreating({ company: next, name: '' })
      return
    }
    setCompany(next)
    setTargets([])
    pickCustomer(null)
    setCompanyError('')
    setTargetError('')
  }

  // 방금 등록한 고객. 회사까지 함께 돌아오므로 두 칸이 한 번에 채워집니다.
  const takeCreated = async (contact: CustomerContactResponse) => {
    setCreating(null)
    const option = toContactOption(contact)
    if (type === '일정') pickCustomer(option)
    else {
      setTargets((prev) => [...prev, option])
      setTargetError('')
    }

    // 고객사 칸은 회사 한 벌을 그대로 들고 있어야 해, 편집으로 열 때와 같이 읽어 옵니다.
    try {
      const { data } = await client.get<CustomerCompanyResponse>(
        `/customer-companies/${contact.company_id}`,
      )
      setCompany({ kind: 'existing', company: data })
      setCompanyError('')
    } catch {
      // 회사를 못 읽어도 고객은 이미 골라졌습니다. 칸만 비어 보입니다.
    }
  }

  // 등록한 단계가 곧 쓸 문서를 가리키면(견적작성·초안작성·발주 접수) 이어서
  // 그 작성 화면까지 열어 줍니다. 저장 직후 무엇을 보여 줄지가 이 값에 달려
  // 있어 submit 보다 위에 둡니다.
  const docName = type === '업무' ? DOCUMENT_BY_TASK_STATUS[taskStatus] : undefined

  const submit = async () => {
    if (form.title.trim() === '') {
      setError('제목을 입력하세요.')
      return
    }

    // 일정 탭의 고객은 없어도 저장됩니다. 다만 회사만 고르고 사람을 비워 두면
    // 고른 회사가 어디에도 남지 않으므로 그때는 사람까지 고르게 합니다.
    if (type === '일정' && company !== null && customer === null) {
      setCustomerError('고객을 선택하세요.')
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
      // 이어서 쓸 문서가 있을 때만 물어볼 것이 남습니다. 그 밖에는 잘 됐다는
      // 말 한마디뿐이라, 확인을 누르게 하지 않고 토스트로 알리며 닫습니다.
      if (mode === 'create' && docName) setSaved(true)
      else {
        if (mode === 'create') showToast('등록되었습니다.')
        onClose()
      }
    } catch {
      setRequestError(
        mode === 'create' ? '일정을 등록하지 못했습니다.' : '일정을 수정하지 못했습니다.',
      )
    } finally {
      setPending(false)
    }
  }

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

  // 등록을 마친 뒤. 문서로 이어질 단계일 때만 여기까지 옵니다. 그 밖의 등록은
  // 토스트로 알리고 이미 닫혔습니다.
  if (saved) {
    return (
      <Modal
        title="일정 등록"
        onClose={onClose}
        footer={
          <>
            <Button type="button" variant="outline" onClick={onClose}>
              취소
            </Button>
            <Button type="button" onClick={goToDocument}>
              이동
            </Button>
          </>
        }
      >
        <div className={styles.saved}>
          <p>등록되었습니다.</p>
          <p>{docName} 작성 화면으로 이동하시겠습니까?</p>
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

            {/* 이름이 겹치는 고객이 흔해, 회사를 먼저 좁힌 뒤 그 안에서 사람을 고릅니다. */}
            <div className={`${styles.field} ${styles.isWide}`}>
              <span className={styles.label}>고객사</span>
              <CompanyAutocomplete
                value={company}
                onChange={pickCompany}
                allowCreate
                invalid={companyError !== ''}
                label="고객사"
              />
              {companyError && <span className={styles.error}>{companyError}</span>}
            </div>

            <div className={`${styles.field} ${styles.isWide}`}>
              <span className={styles.label}>고객</span>
              <ContactPicker
                companyId={companyId(company)}
                value={customer}
                onChange={pickCustomer}
                allowCreate
                onCreate={(name) => setCreating({ company, name })}
                invalid={customerError !== ''}
                label="고객"
              />
              {customerError && (
                <span className={styles.error} role="alert">
                  {customerError}
                </span>
              )}
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
              <CompanyAutocomplete
                value={company}
                onChange={pickCompany}
                allowCreate
                invalid={companyError !== ''}
                label="고객사"
              />
              {companyError && (
                <span className={styles.error} role="alert">
                  {companyError}
                </span>
              )}
            </div>

            <div className={`${styles.field} ${styles.isWide}`}>
              <span className={styles.label}>
                미팅대상자<b aria-hidden="true">*</b>
              </span>
              <ContactPicker
                multiple
                companyId={companyId(company)}
                value={targets}
                onChange={(next) => {
                  setTargets(next)
                  setTargetError('')
                }}
                allowCreate
                onCreate={(name) => setCreating({ company, name })}
                invalid={targetError !== ''}
                label="미팅대상자"
              />
              {targetError && (
                <span className={styles.error} role="alert">
                  {targetError}
                </span>
              )}
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

      {/* 이 모달 본문은 <form> 이라 등록 폼을 그 안에 두면 폼이 겹칩니다. 바깥 스크림의
          backdrop-filter 도 fixed 자식의 기준 상자를 바꿔 위치가 어긋납니다. body 로 꺼냅니다. */}
      {creating &&
        createPortal(
          <CustomerFormModal
            onClose={() => setCreating(null)}
            onCreated={(contact) => void takeCreated(contact)}
            initial={{ name: creating.name }}
            initialCompany={creating.company ?? undefined}
          />,
          document.body,
        )}
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
