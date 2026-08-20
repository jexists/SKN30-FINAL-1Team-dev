// 파일을 올리는 모달입니다. 하는 일이 두 가지인데 고르는 파일과 채우는 값만 다릅니다.
//
//  - target 이 없으면 새 문서 등록. 여러 개를 한 번에 올리고 파일마다 분류를 정합니다.
//  - target 이 있으면 그 문서의 새 버전. 파일 하나만 받고 무엇이 바뀌었는지를 적습니다.
//
// 파일 입력은 AttachmentPanel 과 같은 방식입니다. 기본 입력은 스타일을 맞출 수 없어
// 숨기고 버튼·드롭존으로 엽니다.
import { useRef, useState } from 'react'

import Button from '@/components/Button'
import { TrashIcon, UploadIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import type { DocumentCategory, DocumentLink, SalesDocument } from '@/types'
import { sizeLabel } from '@/utils/attachment'

import { DOCUMENT_CATEGORIES, guessCategory, latestOf, LINK_KINDS } from '../../catalog'

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
  tags: string[]
  note: string
}

interface Props {
  /** 새 버전을 올릴 문서. 없으면 새 문서 등록입니다. */
  target?: SalesDocument
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

export default function UploadModal({ target, submitting = false, onClose, onSubmit }: Props) {
  const isVersion = target !== undefined
  const fileRef = useRef<HTMLInputElement>(null)

  const [picked, setPicked] = useState<Picked[]>([])
  const [dragging, setDragging] = useState(false)
  const [linkKind, setLinkKind] = useState<DocumentLink['kind']>(target?.link.kind ?? 'none')
  const [linkLabel, setLinkLabel] = useState(target?.link.label ?? '')
  const [description, setDescription] = useState(target?.description ?? '')
  const [tags, setTags] = useState(target?.tags.join(', ') ?? '')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')

  const add = (files: FileList | File[]) => {
    const next = Array.from(files).map(pick)
    // 새 버전은 파일 하나만 얹습니다. 여러 개를 떨어뜨리면 마지막 것만 남습니다.
    setPicked((prev) => (isVersion ? next.slice(-1) : [...prev, ...next]))
    setError('')
  }

  const submit = () => {
    if (submitting) return
    if (picked.length === 0) {
      setError('올릴 파일을 고르세요.')
      return
    }

    const link: DocumentLink =
      linkKind === 'none' || linkLabel.trim() === ''
        ? { kind: 'none', label: '' }
        : { kind: linkKind, label: linkLabel.trim() }

    const tagList = tags
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean)

    onSubmit(
      picked.map(({ file, category }) => ({
        file,
        category: target?.category ?? category,
        title: target?.title ?? titleOf(file.name),
        link,
        description: description.trim(),
        tags: tagList,
        note: note.trim(),
      })),
    )
  }

  return (
    <Modal
      title={isVersion ? '새 버전 올리기' : '파일 업로드'}
      description={
        isVersion
          ? `${target.title} · 현재 v${latestOf(target).version}. 올리면 v${latestOf(target).version + 1} 이 됩니다.`
          : '올린 파일은 목록 맨 위에 추가됩니다. 파일 하나가 자료 한 건입니다.'
      }
      size="lg"
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? '업로드 중…' : isVersion ? '새 버전 등록' : '업로드'}
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
          multiple={!isVersion}
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

              {/* 새 버전은 문서의 분류를 그대로 물려받아 고를 것이 없습니다. */}
              {!isVersion && (
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
              )}

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
        {isVersion ? (
          <Field label="변경 내용" wide>
            <input
              value={note}
              placeholder="법무 검토 반영"
              onChange={(event) => setNote(event.target.value)}
            />
          </Field>
        ) : (
          <>
            <Field label="연결 대상">
              <select
                value={linkKind}
                onChange={(event) => setLinkKind(event.target.value as DocumentLink['kind'])}
              >
                {LINK_KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {kind === 'none' ? '연결 안 함' : kind}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="연결 번호·이름">
              <input
                value={linkLabel}
                disabled={linkKind === 'none'}
                placeholder="FM-CT-2026-0059"
                onChange={(event) => setLinkLabel(event.target.value)}
              />
            </Field>

            <Field label="설명" wide>
              <input
                value={description}
                placeholder="목록에서 이 자료가 무엇인지 알아볼 한 줄"
                onChange={(event) => setDescription(event.target.value)}
              />
            </Field>

            <Field label="태그" hint="쉼표로 구분합니다." wide>
              <input
                value={tags}
                placeholder="유지보수, 연간계약"
                onChange={(event) => setTags(event.target.value)}
              />
            </Field>
          </>
        )}
      </div>
    </Modal>
  )
}

interface FieldProps {
  label: string
  hint?: string
  wide?: boolean
  children: React.ReactNode
}

function Field({ label, hint, wide, children }: FieldProps) {
  return (
    <label className={`${styles.field} ${wide ? styles.isWide : ''}`}>
      <span className={styles.label}>
        {label}
        {hint && <i>{hint}</i>}
      </span>
      {children}
    </label>
  )
}
