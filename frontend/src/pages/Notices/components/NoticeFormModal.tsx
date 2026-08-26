// 공지·지시 등록과 수정을 겸하는 폼. 상품 등록 모달(pages/Products)의 뼈대를 그대로 씁니다.
//
// 수정은 바뀐 항목만 보냅니다. 통째로 보내면 그 사이 다른 곳에서 바뀐 값을 되돌려 놓습니다.
import { useState, type ReactNode } from 'react'
import DatePicker, { registerLocale } from 'react-datepicker'
import { ko } from 'date-fns/locale'

import { errorMessage } from '@/api/errorMessage'
import Button from '@/components/Button'
import MemberMultiSelect from '@/components/MemberMultiSelect'
import Modal from '@/components/Modal'
import RichTextEditor from '@/components/RichTextEditor'
import type {
  NoticeCreateRequest,
  NoticeManageResponse,
  NoticePatchRequest,
  NoticeType,
} from '@/types'
import { iso, parseISO, TODAY } from '@/utils/date'

import { TYPE_TABS } from '../noticeCatalog'

import 'react-datepicker/dist/react-datepicker.css'
import styles from '../Notices.module.scss'

registerLocale('ko', ko)

interface Props {
  /** 수정할 글. 주지 않으면 등록입니다. */
  initial?: NoticeManageResponse
  /** 등록할 때 미리 골라 둘 종류. 지금 열려 있는 탭입니다. */
  defaultType: NoticeType
  onClose: () => void
  onSubmit: (payload: NoticeCreateRequest | NoticePatchRequest) => Promise<void>
}

type Errors = Partial<Record<'title' | 'body' | 'targets' | 'period' | 'sortOrder', string>>

/** 태그를 벗긴 글자. 서버 html_sanitize 가 본문이 비었는지 보는 것과 같은 판단입니다. */
function textOf(html: string): string {
  return html
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/g, ' ')
    .trim()
}

export default function NoticeFormModal({ initial, defaultType, onClose, onSubmit }: Props) {
  const editing = initial !== undefined

  const [type, setType] = useState<NoticeType>(initial?.type ?? defaultType)
  const [title, setTitle] = useState(initial?.title ?? '')
  const [tag, setTag] = useState(initial?.tag ?? '')
  const [body, setBody] = useState(initial?.body ?? '')
  const [targetIds, setTargetIds] = useState<string[]>(initial?.target_member_ids ?? [])
  const [start, setStart] = useState<Date>(
    initial ? parseISO(initial.display_start_date) : new Date(TODAY),
  )
  const [end, setEnd] = useState<Date | null>(
    initial?.display_end_date ? parseISO(initial.display_end_date) : null,
  )
  const [hidden, setHidden] = useState(initial?.is_hidden ?? false)
  const [sortOrder, setSortOrder] = useState(String(initial?.sort_order ?? 0))
  const [dueText, setDueText] = useState(initial?.due_text ?? '')

  const [errors, setErrors] = useState<Errors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const submit = async () => {
    if (submitting) return

    // 서버가 내는 오류 코드와 1:1 로 맞춥니다.
    const found: Errors = {}
    if (title.trim() === '') found.title = '제목을 입력하세요.'
    if (textOf(body) === '' && !body.includes('<img')) found.body = '본문을 입력하세요.'
    if (type === 'DIRECTIVE' && targetIds.length === 0) {
      found.targets = '수신자를 한 명 이상 고르세요.'
    }
    if (end !== null && iso(end) < iso(start)) {
      found.period = '종료일은 시작일 이후여야 합니다.'
    }
    const order = Number(sortOrder)
    if (sortOrder.trim() === '' || !Number.isInteger(order) || order < -9999 || order > 9999) {
      found.sortOrder = '-9999~9999 사이의 정수로 입력하세요.'
    }
    setErrors(found)
    if (Object.keys(found).length > 0) return

    const next: NoticeCreateRequest = {
      type,
      title: title.trim(),
      body,
      tag: tag.trim() === '' ? null : tag.trim(),
      due_text: dueText.trim() === '' ? null : dueText.trim(),
      display_start_date: iso(start),
      display_end_date: end === null ? null : iso(end),
      is_hidden: hidden,
      sort_order: order,
      target_member_ids: type === 'DIRECTIVE' ? targetIds : null,
    }

    setSubmitting(true)
    setSubmitError(null)
    try {
      await onSubmit(editing ? changedFields(initial, next) : next)
    } catch (caught: unknown) {
      setSubmitError(
        errorMessage(caught, editing ? '수정하지 못했습니다.' : '등록하지 못했습니다.'),
      )
      setSubmitting(false)
    }
  }

  const close = () => {
    if (!submitting) onClose()
  }

  return (
    <Modal
      title={editing ? '공지 수정' : '공지 등록'}
      size="lg"
      onClose={close}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" disabled={submitting} onClick={close}>
            취소
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? '저장 중…' : editing ? '수정' : '등록'}
          </Button>
        </>
      }
    >
      <div className={styles.grid} aria-busy={submitting}>
        <Field label="종류" required>
          <select
            value={type}
            disabled={submitting}
            onChange={(event) => {
              setType(event.target.value as NoticeType)
              setErrors((previous) => ({ ...previous, targets: undefined }))
            }}
          >
            {TYPE_TABS.map((tab) => (
              <option key={tab.value} value={tab.value}>
                {tab.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="태그">
          <input
            value={tag}
            maxLength={64}
            disabled={submitting}
            placeholder="예: 필독"
            onChange={(event) => setTag(event.target.value)}
          />
        </Field>

        <Field label="제목" required error={errors.title} wide>
          <input
            value={title}
            maxLength={254}
            disabled={submitting}
            placeholder="예: 3분기 영업 목표 안내"
            onChange={(event) => {
              setTitle(event.target.value)
              setErrors((previous) => ({ ...previous, title: undefined }))
            }}
          />
        </Field>

        {type === 'DIRECTIVE' && (
          <div className={`${styles.field} ${styles.isWide}`}>
            <span className={styles.label}>
              수신자<b aria-hidden="true">*</b>
            </span>
            <MemberMultiSelect
              value={targetIds}
              label="수신자"
              placeholder="이름으로 검색"
              disabled={submitting}
              invalid={errors.targets !== undefined}
              onChange={(memberIds) => {
                setTargetIds(memberIds)
                setErrors((previous) => ({ ...previous, targets: undefined }))
              }}
            />
            <span className={styles.hint}>고른 사람만 대시보드에서 이 지시를 봅니다.</span>
            {errors.targets && <span className={styles.error}>{errors.targets}</span>}
          </div>
        )}

        <div className={`${styles.field} ${styles.isWide}`}>
          <span className={styles.label}>
            본문<b aria-hidden="true">*</b>
          </span>
          <RichTextEditor
            value={body}
            disabled={submitting}
            // 폼이 서 있는 동안에는 본문을 갈아 끼우지 않습니다. 갈면 커서가 앞으로
            // 돌아가고 한글 조합이 끊깁니다.
            docKey={0}
            onChange={(html) => {
              setBody(html)
              setErrors((previous) => ({ ...previous, body: undefined }))
            }}
          />
          {errors.body && <span className={styles.error}>{errors.body}</span>}
        </div>

        <div className={`${styles.field} ${styles.isWide}`}>
          <span className={styles.label}>
            게시기간<b aria-hidden="true">*</b>
          </span>
          <div className={styles.period}>
            <DayPicker
              selected={start}
              label="노출 시작일"
              disabled={submitting}
              onChange={(date) => {
                if (date === null) return
                setStart(date)
                setErrors((previous) => ({ ...previous, period: undefined }))
              }}
            />
            <span aria-hidden="true">~</span>
            <DayPicker
              selected={end}
              label="노출 종료일"
              minDate={start}
              isClearable
              disabled={submitting}
              onChange={(date) => {
                setEnd(date)
                setErrors((previous) => ({ ...previous, period: undefined }))
              }}
            />
          </div>
          <span className={styles.hint}>
            시작일과 종료일 모두 그 날을 포함합니다. 종료일을 비우면 무기한입니다.
          </span>
          {errors.period && <span className={styles.error}>{errors.period}</span>}
        </div>

        <Field label="노출 순서" required error={errors.sortOrder}>
          <input
            type="number"
            inputMode="numeric"
            min={-9999}
            max={9999}
            step={1}
            value={sortOrder}
            disabled={submitting}
            onChange={(event) => {
              setSortOrder(event.target.value)
              setErrors((previous) => ({ ...previous, sortOrder: undefined }))
            }}
          />
          <span className={styles.hint}>작을수록 위에 옵니다.</span>
        </Field>

        <Field label="기한 안내">
          <input
            value={dueText}
            maxLength={254}
            disabled={submitting}
            placeholder="예: 이번 주 금요일까지"
            onChange={(event) => setDueText(event.target.value)}
          />
        </Field>

        <div className={`${styles.field} ${styles.isWide}`}>
          <label className={styles.switch}>
            <input
              type="checkbox"
              checked={hidden}
              disabled={submitting}
              onChange={(event) => setHidden(event.target.checked)}
            />
            <span>숨기기</span>
          </label>
          <span className={styles.hint}>
            켜면 이 목록에만 남고 대시보드에서 빠집니다. 글은 지워지지 않습니다.
          </span>
        </div>

        {submitError && (
          <p className={`${styles.error} ${styles.isWide}`} role="alert">
            {submitError}
          </p>
        )}
      </div>
    </Modal>
  )
}

/** 수정 폼이 실제로 바꾼 항목만 골라냅니다. */
function changedFields(
  initial: NoticeManageResponse,
  next: NoticeCreateRequest,
): NoticePatchRequest {
  const patch: NoticePatchRequest = {}
  if (next.type !== initial.type) patch.type = next.type
  if (next.title !== initial.title) patch.title = next.title
  if (next.body !== initial.body) patch.body = next.body
  if (next.tag !== initial.tag) patch.tag = next.tag
  if (next.due_text !== initial.due_text) patch.due_text = next.due_text
  if (next.display_start_date !== initial.display_start_date) {
    patch.display_start_date = next.display_start_date
  }
  if (next.display_end_date !== initial.display_end_date) {
    patch.display_end_date = next.display_end_date
  }
  if (next.is_hidden !== initial.is_hidden) patch.is_hidden = next.is_hidden
  if (next.sort_order !== initial.sort_order) patch.sort_order = next.sort_order

  const nextTargets = next.target_member_ids ?? []
  const sameTargets =
    nextTargets.length === initial.target_member_ids.length &&
    nextTargets.every((id, index) => id === initial.target_member_ids[index])
  // 공지로 바뀌면 서버가 수신자를 비웁니다. 목록을 따로 보내지 않습니다.
  if (next.type === 'DIRECTIVE' && !sameTargets) patch.target_member_ids = nextTargets

  return patch
}

interface DayPickerProps {
  selected: Date | null
  onChange: (date: Date | null) => void
  label: string
  minDate?: Date
  isClearable?: boolean
  disabled?: boolean
}

function DayPicker({ selected, onChange, label, minDate, isClearable, disabled }: DayPickerProps) {
  return (
    <div className={styles.pickerCell}>
      <DatePicker
        selected={selected}
        onChange={onChange}
        minDate={minDate}
        isClearable={isClearable}
        disabled={disabled}
        locale="ko"
        dateFormat="yyyy-MM-dd"
        placeholderText={isClearable ? '무기한' : undefined}
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
