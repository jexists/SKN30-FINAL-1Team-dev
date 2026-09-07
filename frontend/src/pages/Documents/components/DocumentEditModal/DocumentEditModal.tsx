// 올려 둔 자료의 제목·분류·메모·연결을 고치는 모달입니다. 파일은 바꾸지 않습니다.
// 파일 하나가 자료 한 건이라, 다른 파일은 새 자료로 올립니다.
//
// 입력 구성은 UploadModal 과 같습니다. 파일 고르는 자리만 빠집니다.
import { useState } from 'react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import RecordPicker, { type RecordOption } from '@/components/RecordPicker'
import type {
  DocumentCategory,
  DocumentLink,
  ProductResponse,
  SalesDealResponse,
  SalesDocument,
} from '@/types'

import { DOCUMENT_CATEGORIES, LINK_KINDS } from '../../catalog'
import { linkLabel } from '../../columns'
import type { DocumentMeta } from '../../useDocuments'

import styles from './DocumentEditModal.module.scss'

interface Props {
  doc: SalesDocument
  submitting?: boolean
  onClose: () => void
  onSubmit: (meta: Partial<DocumentMeta>) => void
}

/** 고객사·발주 연결은 고르는 목록이 없어 여기서 바꿀 수 없습니다. 값은 그대로 둡니다. */
const isEditableLink = (kind: DocumentLink['kind']) =>
  (LINK_KINDS as readonly string[]).includes(kind)

export default function DocumentEditModal({ doc, submitting = false, onClose, onSubmit }: Props) {
  const linkEditable = isEditableLink(doc.link.kind)

  const [title, setTitle] = useState(doc.title)
  const [category, setCategory] = useState<DocumentCategory>(doc.category)
  const [description, setDescription] = useState(doc.description)
  const [linkKind, setLinkKind] = useState<DocumentLink['kind']>(
    linkEditable ? doc.link.kind : 'none',
  )
  const [linkTarget, setLinkTarget] = useState<RecordOption | null>(
    linkEditable && doc.link.id !== '' ? { id: doc.link.id, label: doc.link.label } : null,
  )
  const [error, setError] = useState('')

  const submit = () => {
    if (submitting) return
    const nextTitle = title.trim()
    if (nextTitle === '') {
      setError('제목을 입력하세요.')
      return
    }

    const meta: Partial<DocumentMeta> = {
      title: nextTitle,
      category,
      description: description.trim(),
    }
    // 바꿀 수 없는 연결은 아예 보내지 않습니다. 훅이 지금 값을 그대로 다시 저장합니다.
    if (linkEditable) {
      meta.link =
        linkKind === 'none' || linkTarget === null
          ? { kind: 'none', id: '', label: '' }
          : { kind: linkKind, id: linkTarget.id, label: linkTarget.label }
    }
    onSubmit(meta)
  }

  return (
    <Modal
      title="자료 수정"
      description="파일은 바꾸지 않습니다. 다른 파일은 새 자료로 올립니다."
      size="lg"
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? '저장 중…' : '저장'}
          </Button>
        </>
      }
    >
      <div className={styles.grid}>
        <Field label="제목" wide>
          <input
            value={title}
            placeholder="목록에 설 이름"
            onChange={(event) => {
              setTitle(event.target.value)
              setError('')
            }}
          />
        </Field>

        <Field label="분류">
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value as DocumentCategory)}
          >
            {DOCUMENT_CATEGORIES.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </Field>

        {linkEditable ? (
          <>
            <Field label="연결 대상" htmlFor={false}>
              <div className={styles.choice} role="radiogroup" aria-label="연결 대상">
                {LINK_KINDS.map((kind) => (
                  <label key={kind} className={styles.choiceItem}>
                    <input
                      type="radio"
                      name="linkKind"
                      className="sr-only"
                      value={kind}
                      checked={linkKind === kind}
                      onChange={() => {
                        setLinkKind(kind)
                        // 종류가 바뀌면 앞서 고른 것은 다른 목록의 것입니다.
                        setLinkTarget(null)
                      }}
                    />
                    <span>{kind === 'none' ? '연결 안 함' : `${kind} 연결`}</span>
                  </label>
                ))}
              </div>
            </Field>

            <Field label={linkKind === 'none' ? '연결 번호·이름' : linkKind} wide>
              {linkKind === '상품' ? (
                <RecordPicker<ProductResponse>
                  path="/products"
                  label="연결할 상품"
                  placeholder="제품 이름으로 검색"
                  emptyText="일치하는 상품이 없습니다."
                  loadingText="상품을 불러오는 중입니다."
                  fallback="상품을 불러오지 못했습니다."
                  value={linkTarget}
                  toOption={(row) => ({ id: row.id, label: row.name })}
                  onChange={setLinkTarget}
                />
              ) : linkKind === '딜' ? (
                <RecordPicker<SalesDealResponse>
                  path="/sales-deals"
                  label="연결할 딜"
                  placeholder="영업번호나 고객사로 검색"
                  emptyText="일치하는 딜이 없습니다."
                  loadingText="딜을 불러오는 중입니다."
                  fallback="딜을 불러오지 못했습니다."
                  value={linkTarget}
                  toOption={(row) => ({
                    id: row.id,
                    label: row.deal_no,
                    note: `${row.customer_company_name} · ${row.title}`,
                  })}
                  onChange={setLinkTarget}
                />
              ) : (
                <input value="" disabled placeholder="연결 대상을 먼저 고르세요" readOnly />
              )}
            </Field>
          </>
        ) : (
          <Field label="연결" hint="여기서 바꿀 수 없습니다">
            <input value={linkLabel(doc)} disabled readOnly />
          </Field>
        )}

        <Field label="메모" wide>
          <input
            value={description}
            placeholder="목록에서 이 자료가 무엇인지 알아볼 한 줄"
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
      </div>

      {error && <p className={styles.error}>{error}</p>}
    </Modal>
  )
}

interface FieldProps {
  label: string
  hint?: string
  wide?: boolean
  /** 라디오 묶음처럼 칸 하나를 가리킬 수 없을 때는 label 대신 div 로 감쌉니다. */
  htmlFor?: boolean
  children: React.ReactNode
}

function Field({ label, hint, wide, htmlFor = true, children }: FieldProps) {
  const Wrapper = htmlFor ? 'label' : 'div'
  return (
    <Wrapper className={`${styles.field} ${wide ? styles.isWide : ''}`}>
      <span className={styles.label}>
        {label}
        {hint && <i>{hint}</i>}
      </span>
      {children}
    </Wrapper>
  )
}
