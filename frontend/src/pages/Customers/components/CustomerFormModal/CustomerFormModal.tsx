import { useEffect, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import { useCurrentUser } from '@/auth/sessionContext'
import AddressField, { type AddressValue } from '@/components/AddressField'
import Button from '@/components/Button'
import CompanyAutocomplete, { type CompanySelection } from '@/components/CompanyAutocomplete'
import MemberMultiSelect from '@/components/MemberMultiSelect'
import Modal from '@/components/Modal'
import { SOURCE_LABEL } from '@/pages/Customers/contact'
import type {
  Customer,
  CustomerCompanyCreateRequest,
  CustomerCompanyResponse,
  CustomerContactCreateRequest,
  CustomerContactResponse,
  CustomerContactUpdateRequest,
  CustomerSourceCode,
} from '@/types'
import { businessNoDigits, formatBusinessNo } from '@/utils/format'

import type { BusinessCardMatch } from '../../businessCard'
import styles from './CustomerFormModal.module.scss'

interface CustomerFormModalProps {
  onClose: () => void
  /** 방금 만든 고객. 부른 쪽이 그대로 골라 둘 수 있게 넘깁니다. */
  onCreated: (contact: CustomerContactResponse, warning?: string) => void
  /**
   * 고칠 고객. 주면 수정 폼이 됩니다. 항목은 등록과 같고 상태만 다루지 않습니다.
   * 상태를 바꾸는 화면이 아직 없어 여기서 새로 만들지 않습니다.
   */
  customer?: Customer
  /** 수정한 결과. 부른 쪽이 목록·상세의 그 줄만 갈아 끼웁니다. */
  onUpdated?: (contact: CustomerContactResponse) => void
  /** 명함에서 읽어 온 값. 사람이 확인하고 고칠 수 있게 칸만 채워 둡니다. */
  initial?: Partial<Draft>
  /** 부른 쪽에서 이미 정해진 회사. 검색창에 미리 올려 둡니다. */
  initialCompany?: CompanySelection
  /**
   * 사업자등록증에서 읽어 온 등록번호. 새로 만드는 회사일 때만 씁니다.
   * 이미 있는 회사는 그 회사의 값이 이깁니다.
   */
  initialBusinessNo?: string
  /**
   * 사업자등록증에서 읽어 온 주소. 새로 만드는 회사일 때만 씁니다.
   * 이미 있는 회사는 그 회사의 값이 이깁니다.
   */
  initialAddress?: AddressValue
  /** 명함 인식 뒤 발견한 기존 담당자 후보. 자동 병합하지 않습니다. */
  duplicateMatches?: BusinessCardMatch[]
  /** 명함 OCR에 사용한 원본. 고객 등록 뒤 자료실에 보관합니다. */
  archiveImage?: File
}

const EMPTY = {
  name: '',
  dept: '',
  title: '',
  email: '',
  phone: '',
  memo: '',
}

type Draft = typeof EMPTY
type ErrorKey = keyof Draft | 'company' | 'businessNo' | 'assignees'
type Errors = Partial<Record<ErrorKey, string>>

interface Form {
  draft: Draft
  company: CompanySelection | null
  businessNo: string
  assigneeIds: string[]
}

function validate({ draft, company, businessNo, assigneeIds }: Form): Errors {
  const errors: Errors = {}
  if (company === null) errors.company = '회사를 검색해서 고르거나 직접 등록해 주세요.'
  if (draft.name.trim() === '') errors.name = '이름을 입력하세요.'
  if (draft.phone.trim() === '') errors.phone = '전화번호를 입력하세요.'
  if (draft.email.trim() !== '' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(draft.email.trim())) {
    errors.email = '이메일 형식이 맞지 않습니다. 예: name@company.com'
  }
  if (businessNo.trim() !== '' && businessNoDigits(businessNo).length !== 10) {
    errors.businessNo = '사업자 등록번호는 숫자 10자리입니다. 예: 123-45-67890'
  }
  if (assigneeIds.length === 0) errors.assignees = '담당자를 한 명 이상 고르세요.'
  return errors
}

const optional = (value: string): string | null => value.trim() || null

const EMPTY_ADDRESS: AddressValue = { postcode: '', address: '', addressDetail: '' }

/** 이미 있는 회사의 주소를 입력칸 모양으로 바꿉니다. */
function companyAddress(company: CustomerCompanyResponse): AddressValue {
  return {
    postcode: company.postcode ?? '',
    address: company.address ?? '',
    addressDetail: company.address_detail ?? '',
  }
}

/** 고른 회사의 id. 새로 등록하기로 한 회사는 이 시점에 만듭니다. */
async function resolveCompanyId(
  company: CompanySelection,
  businessNo: string,
  address: AddressValue,
): Promise<string> {
  if (company.kind === 'existing') return company.company.id

  const payload: CustomerCompanyCreateRequest = {
    name: company.name,
    region_code: null,
    business_no: businessNoDigits(businessNo) || null,
    postcode: optional(address.postcode),
    address: optional(address.address),
    address_detail: optional(address.addressDetail),
  }
  // 그 사이 남이 같은 이름을 만들었으면 백엔드가 기존 행을 돌려줍니다.
  const { data } = await client.post<CustomerCompanyResponse>('/customer-companies', payload)
  return data.id
}

/** 수정 폼의 첫 값. 목록이 이미 들고 있는 고객을 입력칸 모양으로 되돌립니다. */
function customerDraft(customer: Customer): Draft {
  return {
    name: customer.name,
    dept: customer.dept,
    title: customer.title,
    email: customer.email,
    phone: customer.phone,
    memo: customer.memo,
  }
}

export default function CustomerFormModal({
  onClose,
  onCreated,
  customer,
  onUpdated,
  initial,
  initialCompany,
  initialBusinessNo,
  initialAddress,
  duplicateMatches = [],
  archiveImage,
}: CustomerFormModalProps) {
  const { isManager, memberId } = useCurrentUser()
  const editing = customer !== undefined

  const [draft, setDraft] = useState<Draft>(
    customer ? customerDraft(customer) : { ...EMPTY, ...initial },
  )
  // 아직 만나기 전입니다. 방문은 담당자가 다녀온 뒤에 직접 켭니다.
  const [visited, setVisited] = useState(customer?.visited ?? false)
  // 유입경로. 빈 문자열은 미지정입니다.
  const [sourceCode, setSourceCode] = useState<CustomerSourceCode | ''>(customer?.sourceCode ?? '')
  const [company, setCompany] = useState<CompanySelection | null>(initialCompany ?? null)
  const [businessNo, setBusinessNo] = useState(() =>
    initialCompany?.kind === 'existing'
      ? (formatBusinessNo(initialCompany.company.business_no) ?? '')
      : (initialBusinessNo ?? ''),
  )
  const [address, setAddress] = useState<AddressValue>(() =>
    initialCompany?.kind === 'existing'
      ? companyAddress(initialCompany.company)
      : (initialAddress ?? EMPTY_ADDRESS),
  )
  const [assigneeIds, setAssigneeIds] = useState<string[]>(() => {
    if (!customer) return [memberId]
    const owners = customer.owners?.map((owner) => owner.id) ?? []
    return owners.length > 0 ? owners : [customer.ownerMemberId ?? memberId]
  })
  const [errors, setErrors] = useState<Errors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  // 수정 폼은 회사 전체를 받아 와야 검색칸에 올릴 수 있습니다. 목록이 들고 있는 것은
  // 회사 id 와 이름뿐이고, 사업자번호·주소는 회사에 붙어 있습니다.
  const [companyLoading, setCompanyLoading] = useState(editing)

  const companyId = customer?.companyId
  useEffect(() => {
    if (companyId === undefined) return
    const controller = new AbortController()

    setCompanyLoading(true)
    void client
      .get<CustomerCompanyResponse>(`/customer-companies/${companyId}`, {
        signal: controller.signal,
      })
      .then(({ data }) => {
        if (controller.signal.aborted) return
        setCompany({ kind: 'existing', company: data })
        setBusinessNo(formatBusinessNo(data.business_no) ?? '')
        setAddress(companyAddress(data))
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setSubmitError(errorMessage(error, '고객사 정보를 불러오지 못했습니다.'))
      })
      .finally(() => {
        if (!controller.signal.aborted) setCompanyLoading(false)
      })

    return () => controller.abort()
  }, [companyId])

  const clearError = (key: ErrorKey) => {
    setErrors((previous) => ({ ...previous, [key]: undefined }))
    setSubmitError(null)
  }

  const set = (key: keyof Draft, value: string) => {
    setDraft((previous) => ({ ...previous, [key]: value }))
    clearError(key)
  }

  const pickCompany = (selection: CompanySelection | null) => {
    // 기존 회사에서 벗어날 때만 비웁니다. 그 회사의 번호·주소를 다음 회사가 물려받으면
    // 안 되기 때문입니다. 반대로 사업자등록증에서 읽어 채운 값은 회사 이름을 고르고
    // 고치는 동안 그대로 둡니다. 오토컴플리트는 글자마다 선택을 지웁니다.
    const leavingExistingCompany = company?.kind === 'existing'
    setCompany(selection)
    if (selection?.kind === 'existing') {
      // 이미 있는 회사의 사업자번호와 주소는 그 회사의 것입니다. 여기서 고치지 않습니다.
      setBusinessNo(formatBusinessNo(selection.company.business_no) ?? '')
      setAddress(companyAddress(selection.company))
    } else if (leavingExistingCompany) {
      setBusinessNo('')
      setAddress(EMPTY_ADDRESS)
    }
    clearError('company')
    clearError('businessNo')
  }

  const submit = async () => {
    if (submitting || companyLoading) return

    const found = validate({ draft, company, businessNo, assigneeIds })
    setErrors(found)
    if (Object.keys(found).length > 0 || company === null) return

    setSubmitting(true)
    setSubmitError(null)

    try {
      const fields: CustomerContactUpdateRequest = {
        company_id: await resolveCompanyId(company, businessNo, address),
        name: draft.name.trim(),
        department: optional(draft.dept),
        job_title: optional(draft.title),
        email: optional(draft.email),
        phone: draft.phone.trim(),
        source_code: sourceCode === '' ? null : sourceCode,
        memo: optional(draft.memo),
        visited,
        // 팀원은 담당자를 고를 수 없습니다. 백엔드가 등록한 사람으로 채웁니다.
        ...(isManager ? { assignee_member_ids: assigneeIds } : {}),
      }

      if (customer) {
        const { data } = await client.patch<CustomerContactResponse>(
          `/customer-contacts/${customer.id}`,
          fields,
        )
        setSubmitting(false)
        onUpdated?.(data)
        return
      }

      // 상태는 등록할 때만 정해집니다. 수정 폼에는 상태 칸이 없습니다.
      const payload: CustomerContactCreateRequest = { ...fields, status_code: 'new' }
      const { data } = await client.post<CustomerContactResponse>('/customer-contacts', payload)
      let warning: string | undefined
      if (archiveImage) {
        const archive = new FormData()
        archive.append('contact_id', data.id)
        archive.append('image', archiveImage)
        try {
          await client.post('/business-cards/archive', archive)
        } catch {
          // 고객 등록은 완료됐으므로 원본 보관 실패가 등록 자체를 되돌리지는 않습니다.
          warning =
            '고객은 등록됐지만 명함 원본 보관에 실패했습니다. 자료실에 다시 업로드해 주세요.'
        }
      }
      setSubmitting(false)
      onCreated(data, warning)
    } catch (error: unknown) {
      setSubmitError(
        errorMessage(
          error,
          editing ? '고객 정보를 수정하지 못했습니다.' : '고객을 등록하지 못했습니다.',
        ),
      )
      setSubmitting(false)
    }
  }

  const close = () => {
    if (!submitting) onClose()
  }

  return (
    <Modal
      title={editing ? '고객 수정' : '고객 등록'}
      onClose={close}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" disabled={submitting} onClick={close}>
            취소
          </Button>
          <Button type="submit" disabled={submitting || companyLoading}>
            {editing ? (submitting ? '저장 중…' : '저장') : submitting ? '등록 중…' : '고객 등록'}
          </Button>
        </>
      }
    >
      {duplicateMatches.length > 0 && (
        <div className={styles.duplicateNotice} role="alert">
          <strong>기존 고객 후보가 있습니다.</strong>
          <ul>
            {duplicateMatches.map((match) => (
              <li key={match.contact_id}>
                {match.company_name} · {match.name} · {match.phone}
              </li>
            ))}
          </ul>
          <span>기존 고객인지 확인한 뒤 등록하세요. 자동으로 합치지 않습니다.</span>
        </div>
      )}
      <div className={styles.grid} aria-busy={submitting}>
        <Field label="회사" required error={errors.company} htmlFor={false}>
          <CompanyAutocomplete
            value={company}
            onChange={pickCompany}
            allowCreate
            disabled={submitting || companyLoading}
            invalid={errors.company !== undefined}
          />
        </Field>

        <Field label="사업자 등록번호" error={errors.businessNo}>
          <input
            value={businessNo}
            placeholder="123-45-67890"
            maxLength={12}
            // 이미 있는 회사는 그 회사의 값을 보여 주기만 합니다.
            readOnly={company?.kind === 'existing'}
            // 회사를 고르기 전이라도, 등록증에서 읽어 온 값은 고칠 수 있어야 합니다.
            disabled={submitting || (company === null && businessNo === '')}
            onChange={(event) => {
              setBusinessNo(event.target.value)
              clearError('businessNo')
            }}
          />
        </Field>

        {/* 주소는 회사에 붙는 값입니다. 이미 있는 회사면 그 회사의 주소를 보여 주기만 합니다. */}
        <Field label="주소" wide htmlFor={false}>
          <AddressField
            value={address}
            onChange={setAddress}
            readOnly={company?.kind === 'existing'}
            // 등록증에서 읽어 온 주소가 있으면 회사를 고르기 전에도 다시 고를 수 있습니다.
            disabled={submitting || (company === null && address.address === '')}
          />
        </Field>

        <Field label="이름" required error={errors.name}>
          <input
            value={draft.name}
            maxLength={254}
            disabled={submitting}
            onChange={(event) => set('name', event.target.value)}
          />
        </Field>

        <Field label="전화" required error={errors.phone}>
          <input
            type="tel"
            value={draft.phone}
            placeholder="02-000-0000"
            maxLength={50}
            disabled={submitting}
            onChange={(event) => set('phone', event.target.value)}
          />
        </Field>

        <Field label="부서">
          <input
            value={draft.dept}
            placeholder="부서 이름"
            maxLength={254}
            disabled={submitting}
            onChange={(event) => set('dept', event.target.value)}
          />
        </Field>

        <Field label="직함">
          <input
            value={draft.title}
            placeholder="과장"
            maxLength={254}
            disabled={submitting}
            onChange={(event) => set('title', event.target.value)}
          />
        </Field>

        <Field label="이메일" error={errors.email}>
          <input
            type="email"
            value={draft.email}
            placeholder="name@company.com"
            maxLength={254}
            disabled={submitting}
            onChange={(event) => set('email', event.target.value)}
          />
        </Field>

        <Field label="방문여부" htmlFor={false}>
          <div className={styles.choice} role="radiogroup" aria-label="방문여부">
            {[false, true].map((value) => (
              <label key={String(value)} className={styles.choiceItem}>
                <input
                  type="radio"
                  name="visited"
                  className="sr-only"
                  checked={visited === value}
                  disabled={submitting}
                  onChange={() => setVisited(value)}
                />
                <span>{value ? '방문' : '미방문'}</span>
              </label>
            ))}
          </div>
        </Field>

        <Field label="유입경로">
          <select
            value={sourceCode}
            disabled={submitting}
            onChange={(event) => setSourceCode(event.target.value as CustomerSourceCode | '')}
          >
            <option value="">미지정</option>
            {Object.entries(SOURCE_LABEL).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </Field>

        {/*
         * 담당자를 정할 수 있는 건 팀장뿐입니다. 팀원이 등록하면 본인이 담당자가 됩니다.
         * 칩이 늘면 칸이 세로로 자라 옆 칸과 어긋나므로 한 줄을 통째로 씁니다.
         */}
        {isManager && (
          <Field label="담당자" required error={errors.assignees} wide htmlFor={false}>
            <MemberMultiSelect
              value={assigneeIds}
              onChange={(next) => {
                setAssigneeIds(next)
                clearError('assignees')
              }}
              disabled={submitting}
              invalid={errors.assignees !== undefined}
              firstChipHint="첫 번째 담당자가 대표 담당자입니다."
            />
          </Field>
        )}

        <Field label="메모" wide>
          <textarea
            rows={3}
            value={draft.memo}
            placeholder="참고사항"
            maxLength={5000}
            disabled={submitting}
            onChange={(event) => set('memo', event.target.value)}
          />
        </Field>
      </div>

      {submitError && (
        <p className={styles.error} role="alert">
          {submitError}
        </p>
      )}
    </Modal>
  )
}

interface FieldProps {
  label: string
  required?: boolean
  error?: string
  wide?: boolean
  /**
   * label 로 감쌀지. 검색해서 고르는 입력은 안에 버튼이 있어, label 을 누르면 버튼이
   * 눌리거나 포커스가 엉킵니다. 그런 칸은 false 로 두고 div 로 감쌉니다.
   */
  htmlFor?: boolean
  children: React.ReactNode
}

function Field({ label, required, error, wide, htmlFor = true, children }: FieldProps) {
  const Wrapper = htmlFor ? 'label' : 'div'
  return (
    <Wrapper className={`${styles.field} ${wide ? styles.isWide : ''}`}>
      <span className={styles.label}>
        {label}
        {required && <b aria-hidden="true">*</b>}
      </span>
      {children}
      {error && <span className={styles.error}>{error}</span>}
    </Wrapper>
  )
}
