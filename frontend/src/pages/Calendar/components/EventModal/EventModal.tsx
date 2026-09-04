import { useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

import { client } from '@/api/client'
import Button from '@/components/Button'
import CompanyAutocomplete, { type CompanySelection } from '@/components/CompanyAutocomplete'
import ContactPicker, { toContactOption, type ContactOption } from '@/components/ContactPicker'
import DateTimePicker from '@/components/DateTimePicker'
import { TrashIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import RecordPicker, { type RecordOption } from '@/components/RecordPicker'
import CustomerFormModal from '@/pages/Customers/components/CustomerFormModal'
import SalesDealForm from '@/pages/Deals/SalesDealForm'
import useQuickDealCreate from '@/pages/Deals/useQuickDealCreate'
import { showToast } from '@/shared/toast'
import type {
  CalendarEvent,
  CustomerCompanyResponse,
  CustomerContactResponse,
  PageResponse,
  SalesDealResponse,
} from '@/types'
import { iso, parseISO } from '@/utils/date'

import styles from './EventModal.module.scss'

interface Props {
  /** 열 때의 일정. 편집은 이 모달 안에서만 하고 저장할 때 한 번에 올립니다. */
  draft: CalendarEvent
  /** 새로 만드는 중이면 지울 것이 아직 없어 삭제를 감춥니다. */
  mode?: 'edit' | 'create'
  onClose: () => void
  /** 저장이 끝나야 모달이 닫힙니다. 실패는 반드시 reject 로 돌려주세요. */
  onSave: (event: CalendarEvent) => Promise<void>
  onDelete?: (id: string) => void | Promise<void>
}

/** 고객사 칸이 들고 있는 회사의 id. 직접 등록은 쓰지 않아 늘 이미 있는 회사입니다. */
function companyId(selection: CompanySelection | null): string | null {
  return selection?.kind === 'existing' ? selection.company.id : null
}

// 아직 끝나지 않은 딜. 취소·납품 완료까지 간 건에 새 미팅을 붙일 일은 없습니다.
const OPEN_DEAL_PHASES = ['sales', 'quote', 'contract', 'order']

/** 딜 칸에 적는 이름. 계약번호가 있으면 그것이 사람들이 부르는 번호입니다. */
function toDealOption(deal: SalesDealResponse): RecordOption {
  return { id: deal.id, label: deal.contract_no ?? deal.deal_no, note: deal.title }
}

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

/**
 * 일정 한 건을 등록·수정합니다.
 *
 * 묻는 것은 제목·날짜·고객사·고객·딜·장소·메모 일곱 가지입니다. 상태 태그는 이 자리에서
 * 고르지 않고, 새로 만드는 일정은 태그 없이 미팅으로 저장됩니다. 고쳐 쓰려고 연 일정은
 * 원래 붙어 있던 태그를 그대로 들고 갑니다.
 *
 * 딜은 비워 둘 수 없습니다. 딜이 없으면 그 일정은 파이프라인에도 계약관리 에이전트에도
 * 걸리지 않아 어디에서도 다시 찾을 수 없습니다. 고를 딜이 아직 없는 신규 고객사는
 * 고객 등록과 같은 방식으로 이 자리에서 딜을 만들어 이어 갑니다.
 */
export default function EventModal({ draft, mode = 'edit', onClose, onSave, onDelete }: Props) {
  const [form, setForm] = useState<CalendarEvent>(draft)
  const [start, setStart] = useState(() => at(draft.date, draft.time))
  const [end, setEnd] = useState(
    () => new Date(at(draft.date, draft.time).getTime() + parseDur(draft.dur) * MINUTE),
  )
  const [hasEnd, setHasEnd] = useState(draft.endsAt !== null)
  // 이름이 겹치는 고객이 흔해, 회사를 먼저 좁힌 뒤 그 안에서 사람을 고릅니다.
  const [company, setCompany] = useState<CompanySelection | null>(null)
  const [customer, setCustomer] = useState<ContactOption | null>(null)
  // 아직 없는 고객사·고객은 이 자리에서 등록합니다. null 이면 등록 모달이 닫힌 상태입니다.
  const [creating, setCreating] = useState<{
    company: CompanySelection | null
    name: string
  } | null>(null)
  // 이 일정이 무엇에 대한 것인지. 고른 회사의 딜만 후보입니다.
  const [deal, setDeal] = useState<RecordOption | null>(null)
  // 고를 딜이 없을 때 이 자리에서 만듭니다. 파이프라인을 못 읽으면 열지 않습니다.
  const [creatingDeal, setCreatingDeal] = useState(false)
  const quickDeal = useQuickDealCreate()

  const [error, setError] = useState('')
  const [customerError, setCustomerError] = useState('')
  const [companyError, setCompanyError] = useState('')
  const [dealError, setDealError] = useState('')
  const [rangeError, setRangeError] = useState('')
  const [requestError, setRequestError] = useState('')
  const [pending, setPending] = useState(false)

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

  // 새로 만드는 일정에서 회사를 고르면, 그 회사에 열린 딜이 하나뿐인지 봅니다. 하나뿐이면
  // 고를 여지가 없으므로 미리 채워 둡니다 — 서버가 조용히 붙이지 않고 칸에 보여 주는 쪽이라,
  // 인사차 방문처럼 딜과 무관한 일정이면 ⓧ 로 지우고 저장하면 됩니다.
  const pickedCompanyId = companyId(company)
  useEffect(() => {
    if (mode !== 'create' || pickedCompanyId === null || deal !== null) return
    const controller = new AbortController()

    void client
      .get<PageResponse<SalesDealResponse>>('/sales-deals', {
        params: {
          customer_company_id: pickedCompanyId,
          phase_code: OPEN_DEAL_PHASES,
          // 하나뿐인지만 보면 되므로 두 건까지만 받습니다.
          limit: 2,
        },
        signal: controller.signal,
      })
      .then(({ data }) => {
        if (controller.signal.aborted || data.items.length !== 1) return
        pickDeal(toDealOption(data.items[0]))
      })
      // 못 받으면 칸을 비운 채로 둡니다. 고르는 것은 언제든 사람이 할 수 있습니다.
      .catch(() => {})

    return () => controller.abort()
    // deal 은 넣지 않습니다 — 채운 뒤 다시 돌아 이미 고른 값을 덮어쓰지 않게 합니다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, pickedCompanyId])

  // 고쳐 쓰려고 연 일정. 저장된 것은 딜 id 하나뿐이라 칸에 번호를 보이려면 한 건을
  // 읽어야 합니다. 실패하면 빈 칸으로 두고 다시 고르게 합니다.
  const savedDealId = draft.salesDealId ?? null
  useEffect(() => {
    if (savedDealId === null) return
    const controller = new AbortController()

    void client
      .get<SalesDealResponse>(`/sales-deals/${savedDealId}`, { signal: controller.signal })
      .then(({ data }) => {
        if (controller.signal.aborted) return
        setDeal(toDealOption(data))
      })
      .catch(() => {})

    return () => controller.abort()
  }, [savedDealId])

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

  // 회사를 바꾸면 그 전 회사 사람이 고객으로 남아 있으면 안 됩니다.
  const pickCompany = (next: CompanySelection | null) => {
    // 아직 없는 회사를 고른 것은 "여기 없으니 새로 만들겠다" 는 뜻입니다. 일정에 붙는 것은
    // 회사가 아니라 그 회사의 고객이라, 회사만 만들어 두면 일정에는 아무것도 남지 않습니다.
    // 그래서 곧바로 고객 등록으로 넘겨 회사와 사람을 한 번에 만듭니다.
    if (next?.kind === 'new') {
      setCreating({ company: next, name: '' })
      return
    }
    setCompany(next)
    pickCustomer(null)
    pickDeal(null)
    setCompanyError('')
  }

  // 딜을 고르면 일정이 무엇에 대한 것인지가 정해집니다. 폼은 id 만 올립니다.
  const pickDeal = (found: RecordOption | null) => {
    setDeal(found)
    setDealError('')
    set('salesDealId', found?.id ?? null)
  }

  // 방금 등록한 고객. 회사까지 함께 돌아오므로 두 칸이 한 번에 채워집니다.
  const takeCreated = async (contact: CustomerContactResponse) => {
    setCreating(null)
    pickCustomer(toContactOption(contact))

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

  // 방금 만든 딜. 이 자리에서 만든 것은 곧바로 이 일정의 딜이 됩니다.
  const takeCreatedDeal = (created: { id: string; no: string; title: string }) => {
    setCreatingDeal(false)
    pickDeal({ id: created.id, label: created.no, note: created.title })
  }

  const submit = async () => {
    if (form.title.trim() === '') {
      setError('제목을 입력하세요.')
      return
    }

    // 일정에 실제로 붙는 것은 회사가 아니라 그 회사의 고객입니다. 회사만 고르고 사람을
    // 비워 두면 고른 회사가 어디에도 남지 않으므로 둘 다 고르게 합니다.
    if (company === null) {
      setCompanyError('고객사를 선택하세요.')
      return
    }
    if (customer === null) {
      setCustomerError('고객을 선택하세요.')
      return
    }

    // 소요는 시작과 끝의 차이입니다. 목록·드로어는 이 문구만 읽습니다.
    const minutes = Math.round((end.getTime() - start.getTime()) / MINUTE)
    if (hasEnd && minutes <= 0) {
      setRangeError('종료가 시작보다 빠릅니다.')
      return
    }

    setPending(true)
    setRequestError('')
    try {
      // stage·kind 는 폼이 정하지 않습니다. 새 일정은 draft 가 들고 온 미팅 그대로,
      // 고쳐 쓰는 일정은 원래 붙어 있던 태그 그대로 올라갑니다.
      await onSave({
        ...form,
        title: form.title.trim(),
        date: iso(start),
        time: hhmm(start),
        dur: form.allDay ? '종일' : hasEnd ? durLabel(minutes) : '',
        allDay: form.allDay ?? false,
      })
      if (mode === 'create') showToast('등록되었습니다.')
      onClose()
    } catch {
      setRequestError(
        mode === 'create' ? '일정을 등록하지 못했습니다.' : '일정을 수정하지 못했습니다.',
      )
    } finally {
      setPending(false)
    }
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
            <DateTimePicker selected={start} onChange={moveStart} label="시작" />
            <DateTimePicker
              selected={end}
              onChange={(date) => {
                if (!date) return
                setEnd(date)
                setHasEnd(true)
              }}
              label="종료"
              minDate={start}
            />
          </div>
          {rangeError && <span className={styles.error}>{rangeError}</span>}
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
            고객<b aria-hidden="true">*</b>
          </span>
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

        <div className={`${styles.field} ${styles.isWide}`}>
          <span className={styles.label}>
            딜<span className={styles.optional}>선택</span>
          </span>
          <RecordPicker<SalesDealResponse>
            // 회사를 바꾸면 칸을 새로 답니다. RecordPicker 는 값이 null 로 비어도 입력칸의
            // 글자를 지우지 않습니다 — 고른 뒤 글자를 고치는 중에 지워지면 안 되기 때문입니다.
            // 그래서 회사가 바뀔 때는 그 규칙을 우회해 앞 회사의 딜 번호가 남지 않게 합니다.
            key={companyId(company) ?? 'no-company'}
            path="/sales-deals"
            label="딜"
            placeholder={
              companyId(company) === null ? '고객사를 먼저 선택하세요' : '계약번호나 제목으로 검색'
            }
            emptyText="일치하는 딜이 없습니다."
            loadingText="딜을 불러오는 중입니다."
            fallback="딜을 불러오지 못했습니다."
            // 회사는 서버가 거릅니다. 전건을 받아 화면에서 거르면 첫 쪽이 30건으로 끊깁니다.
            params={{ customer_company_id: companyId(company) ?? '' }}
            value={deal}
            disabled={pending || companyId(company) === null}
            invalid={dealError !== ''}
            toOption={toDealOption}
            onChange={(next) => pickDeal(next)}
          />
          {/* 신규 고객사는 아직 딜이 없습니다. 여기서 막히지 않게 그 자리에서 만듭니다.
              딜에도 담당자가 필요하고 그 사람은 이 일정의 고객과 같아야 하므로, 고객을
              고르기 전에는 만들 수 없다고 알려 줍니다. */}
          {companyId(company) !== null &&
            quickDeal.ready &&
            (customer === null ? (
              <span className={styles.createDealHint}>고객을 고르면 새 딜을 만들 수 있습니다.</span>
            ) : (
              <button
                type="button"
                className={styles.createDeal}
                disabled={pending}
                onClick={() => setCreatingDeal(true)}
              >
                + 새 딜 만들기
              </button>
            ))}
          {dealError && (
            <span className={styles.error} role="alert">
              {dealError}
            </span>
          )}
        </div>

        <Field label="장소" wide>
          <input
            value={form.place ?? ''}
            placeholder="미팅 장소"
            onChange={(e) => set('place', e.target.value)}
          />
        </Field>

        <Field label="메모" wide>
          <textarea
            rows={3}
            value={form.brief ?? ''}
            placeholder="참고사항"
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

      {creatingDeal &&
        company?.kind === 'existing' &&
        createPortal(
          <SalesDealForm
            columns={quickDeal.columns}
            initialCompany={company.company}
            initialContact={customer ?? undefined}
            onClose={() => setCreatingDeal(false)}
            onSubmit={async (input) => {
              const created = await quickDeal.createDeal(input)
              takeCreatedDeal({
                id: created.id,
                no: created.contractNo ?? created.no,
                title: created.title,
              })
            }}
          />,
          document.body,
        )}
    </Modal>
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
