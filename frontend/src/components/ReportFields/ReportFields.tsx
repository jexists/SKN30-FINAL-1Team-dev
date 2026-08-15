import type { ReportFieldDef, ReportTemplate } from '@/types'

import styles from './ReportFields.module.scss'

interface Props {
  template: ReportTemplate
  values: Record<string, string>
  /** 읽기 모드면 입력 대신 값만 보여 줍니다. 비어 있는 항목은 빠집니다. */
  readOnly?: boolean
  /** AI 가 채운 항목. 배지가 붙습니다. */
  aiFilledIds?: ReadonlySet<string>
  onChange?: (id: string, value: string) => void
}

function Control({
  field,
  value,
  onChange,
}: {
  field: ReportFieldDef
  value: string
  onChange?: (id: string, value: string) => void
}) {
  const shared = {
    id: field.id,
    value,
    placeholder: field.placeholder,
    onChange: (event: { target: { value: string } }) => onChange?.(field.id, event.target.value),
  }

  if (field.type === 'textarea') return <textarea {...shared} rows={4} />
  if (field.type === 'select') {
    return (
      <select {...shared}>
        {field.options?.map((option) => (
          <option key={option}>{option}</option>
        ))}
      </select>
    )
  }
  return <input {...shared} type="text" />
}

export default function ReportFields({
  template,
  values,
  readOnly = false,
  aiFilledIds,
  onChange,
}: Props) {
  const fields = readOnly
    ? template.fields.filter((field) => values[field.id]?.trim())
    : template.fields

  if (readOnly && fields.length === 0) {
    return <p className={styles.blank}>작성된 내용이 없습니다.</p>
  }

  return (
    <div className={styles.fields}>
      {fields.map((field) => (
        <div key={field.id} className={styles.field}>
          <div className={styles.head}>
            <label className={styles.label} htmlFor={readOnly ? undefined : field.id}>
              {field.label}
              {field.required && !readOnly && <b aria-hidden="true">*</b>}
            </label>
            {aiFilledIds?.has(field.id) && <span className={styles.ai}>AI 작성</span>}
          </div>

          {field.hint && !readOnly && <p className={styles.hint}>{field.hint}</p>}

          {readOnly ? (
            <p className={styles.value}>{values[field.id]}</p>
          ) : (
            <Control field={field} value={values[field.id] ?? ''} onChange={onChange} />
          )}
        </div>
      ))}
    </div>
  )
}
