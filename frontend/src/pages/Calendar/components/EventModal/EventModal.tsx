import { useState, type ReactNode } from 'react'

import Button from '@/components/Button'
import { TrashIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import { EXTERNAL_STATUSES, INTERNAL_STATUSES, KIND_LABEL } from '@/shared/agenda'
import type { AgendaKind, CalendarEvent } from '@/types'

import styles from './EventModal.module.scss'

interface Props {
  /** 열 때의 일정. 편집은 이 모달 안에서만 하고 저장할 때 한 번에 올립니다. */
  draft: CalendarEvent
  /** 새로 만드는 중이면 지울 것이 아직 없어 삭제를 감춥니다. */
  mode?: 'edit' | 'create'
  onClose: () => void
  onSave: (event: CalendarEvent) => void
  onDelete?: (id: string) => void
}

const KINDS = Object.keys(KIND_LABEL) as AgendaKind[]

export default function EventModal({ draft, mode = 'edit', onClose, onSave, onDelete }: Props) {
  const [form, setForm] = useState<CalendarEvent>(draft)
  const [error, setError] = useState('')

  const set = <K extends keyof CalendarEvent>(key: K, value: CalendarEvent[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const submit = () => {
    if (form.title.trim() === '') {
      setError('제목을 입력하세요.')
      return
    }
    onSave({ ...form, title: form.title.trim() })
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
        <Field label="제목" required error={error} wide>
          <input
            value={form.title}
            placeholder="CardioView X7 도입 후속 미팅"
            onChange={(e) => set('title', e.target.value)}
          />
        </Field>

        <Field label="날짜">
          <input type="date" value={form.date} onChange={(e) => set('date', e.target.value)} />
        </Field>

        <Field label="시작">
          <input type="time" value={form.time} onChange={(e) => set('time', e.target.value)} />
        </Field>

        <Field label="소요">
          <input value={form.dur} placeholder="40분" onChange={(e) => set('dur', e.target.value)} />
        </Field>

        <Field label="종류">
          <select value={form.kind} onChange={(e) => set('kind', e.target.value as AgendaKind)}>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {KIND_LABEL[k]}
              </option>
            ))}
          </select>
        </Field>

        {/* 상태는 외부(고객 대상)와 내부(사내)로 갈립니다. 목록의 태그 색이 이 값을 따릅니다. */}
        <Field label="상태">
          <select
            value={form.stage ?? ''}
            onChange={(e) => set('stage', (e.target.value || undefined) as CalendarEvent['stage'])}
          >
            <option value="">선택 안 함</option>
            <optgroup label="외부">
              {EXTERNAL_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </optgroup>
            <optgroup label="내부">
              {INTERNAL_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </optgroup>
          </select>
        </Field>

        <Field label="고객사·기관">
          <input
            value={form.hospital ?? ''}
            placeholder="한빛대학교병원"
            onChange={(e) => set('hospital', e.target.value)}
          />
        </Field>

        <Field label="부서">
          <input
            value={form.dept ?? ''}
            placeholder="순환기내과"
            onChange={(e) => set('dept', e.target.value)}
          />
        </Field>

        <Field label="담당자">
          <input
            value={form.contact ?? ''}
            placeholder="박서준 교수"
            onChange={(e) => set('contact', e.target.value)}
          />
        </Field>

        <Field label="장소">
          <input
            value={form.place ?? ''}
            placeholder="본관 3층 회의실"
            onChange={(e) => set('place', e.target.value)}
          />
        </Field>

        <Field label="메모" wide>
          <textarea
            rows={3}
            value={form.brief ?? ''}
            placeholder="이번 미팅에서 확인할 것"
            onChange={(e) => set('brief', e.target.value)}
          />
        </Field>
      </div>
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
