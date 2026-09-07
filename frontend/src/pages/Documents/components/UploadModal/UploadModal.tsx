// 자료를 등록하는 모달입니다. 여러 개를 한 번에 올리고 파일마다 분류를 정합니다.
// 파일 하나가 자료 한 건이라 올린 뒤에 파일을 바꿔 끼우지 않습니다.
//
// 파일 입력은 AttachmentPanel 과 같은 방식입니다. 기본 입력은 스타일을 맞출 수 없어
// 숨기고 버튼·드롭존으로 엽니다.
import { useRef, useState } from 'react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import RecordPicker, { type RecordOption } from '@/components/RecordPicker'
import { TrashIcon, UploadIcon } from '@/components/icons'
import type { DocumentCategory, DocumentLink, ProductResponse, SalesDealResponse } from '@/types'
import { sizeLabel } from '@/utils/attachment'

import { DOCUMENT_CATEGORIES, guessCategory, LINK_KINDS } from '../../catalog'

import styles from './UploadModal.module.scss'

/** 올릴 파일 한 줄. 분류는 파일명으로 찍어 두고 사람이 고칠 수 있게 둡니다. */
interface Picked {
  /** 같은 파일을 두 번 골라도 줄이 구분되도록 붙이는 임시 키입니다. */
  key: string
  file: File
  category: DocumentCategory
}

export interface UploadResult {
  file: File
  category: DocumentCategory
  title: string
  link: DocumentLink
  description: string
}

interface Props {
  submitting?: boolean
  onClose: () => void
  /** 고른 파일 수만큼 한 건씩 넘어옵니다. */
  onSubmit: (results: UploadResult[]) => void
}

/** 확장자를 뗀 파일명. 문서 제목의 기본값입니다. */
const titleOf = (fileName: string) => fileName.replace(/\.[^.]+$/, '')

const pick = (file: File): Picked => ({
  key: `${file.name}-${file.lastModified}-${Math.random().toString(36).slice(2, 8)}`,
  file,
  category: guessCategory(file.name),
})

export default function UploadModal({ submitting = false, onClose, onSubmit }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)

  const [picked, setPicked] = useState<Picked[]>([])
  const [dragging, setDragging] = useState(false)
  const [linkKind, setLinkKind] = useState<DocumentLink['kind']>('none')
  const [linkTarget, setLinkTarget] = useState<RecordOption | null>(null)
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')

  const add = (files: FileList | File[]) => {
    const next = Array.from(files).map(pick)
    setPicked((prev) => [...prev, ...next])
    setError('')
  }

  const submit = () => {
    if (submitting) return
    if (picked.length === 0) {
      setError('올릴 파일을 고르세요.')
      return
    }

    const link: DocumentLink =
      linkKind === 'none' || linkTarget === null
        ? { kind: 'none', id: '', label: '' }
        : { kind: linkKind, id: linkTarget.id, label: linkTarget.label }

    onSubmit(
      picked.map(({ file, category }) => ({
        file,
        category,
        title: titleOf(file.name),
        link,
        description: description.trim(),
      })),
    )
  }

  return (
    <Modal
      title="파일 업로드"
      description="올린 파일은 목록 맨 위에 추가됩니다. 파일 하나가 자료 한 건입니다."
      size="lg"
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? '업로드 중…' : '업로드'}
          </Button>
        </>
      }
    >
      {/* 끌어다 놓기와 고르기 둘 다 됩니다. 브라우저가 파일을 새 탭으로 여는 기본
          동작을 막아야 해서 dragOver 에서도 preventDefault 를 합니다. */}
      <div
        className={[styles.drop, dragging ? styles.isDragging : ''].filter(Boolean).join(' ')}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          if (event.dataTransfer.files.length > 0) add(event.dataTransfer.files)
        }}
      >
        <UploadIcon width={22} height={22} strokeWidth={1.5} />
        <p>여기로 파일을 끌어다 놓거나</p>
        <Button type="button" variant="outline" onClick={() => fileRef.current?.click()}>
          파일 고르기
        </Button>

        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx,.pptx,.html,.htm,.txt,.md,.markdown,.hwp"
          multiple
          className="sr-only"
          onChange={(event) => {
            if (event.target.files) add(event.target.files)
            // 같은 파일을 다시 골라도 change 가 나게 비웁니다.
            event.target.value = ''
          }}
        />
      </div>

      {error && <p className={styles.error}>{error}</p>}

      {picked.length > 0 && (
        <ul className={styles.list}>
          {picked.map((item) => (
            <li key={item.key} className={styles.item}>
              <div className={styles.file}>
                <strong className={styles.name}>{item.file.name}</strong>
                <span className={styles.size}>{sizeLabel(item.file.size)}</span>
              </div>

              <select
                className={styles.category}
                value={item.category}
                aria-label={`${item.file.name} 분류`}
                onChange={(event) =>
                  setPicked((prev) =>
                    prev.map((row) =>
                      row.key === item.key
                        ? { ...row, category: event.target.value as DocumentCategory }
                        : row,
                    ),
                  )
                }
              >
                {DOCUMENT_CATEGORIES.map((category) => (
                  <option key={category}>{category}</option>
                ))}
              </select>

              <button
                type="button"
                className={styles.remove}
                aria-label={`${item.file.name} 빼기`}
                onClick={() => setPicked((prev) => prev.filter((row) => row.key !== item.key))}
              >
                <TrashIcon />
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className={styles.grid}>
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

        <Field label={linkKind === 'none' ? '연결 번호·이름' : linkKind}>
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

        <Field label="메모" wide>
          <input
            value={description}
            placeholder="목록에서 이 자료가 무엇인지 알아볼 한 줄"
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
      </div>
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
