// 자료를 등록하는 모달입니다. 여러 개를 한 번에 올리고 분류·연결·메모는 한 번만 정합니다.
// 파일 하나가 자료 한 건이라 올린 뒤에 파일을 바꿔 끼우지 않습니다.
//
// 파일 입력은 AttachmentPanel 과 같은 방식입니다. 기본 입력은 스타일을 맞출 수 없어
// 숨기고 버튼·드롭존으로 엽니다.
import { useRef, useState } from 'react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import RecordPicker, { type RecordOption } from '@/components/RecordPicker'
import Tabs from '@/components/Tabs'
import { TrashIcon, UploadIcon } from '@/components/icons'
import RecognitionLoading from '@/pages/Customers/components/RecognitionLoading'
import { showToast } from '@/shared/toast'
import type { DocumentCategory, DocumentLink, ProductResponse, SalesDealResponse } from '@/types'
import { sizeLabel } from '@/utils/attachment'

import {
  categoryFromFileName,
  clampCategory,
  needsDeal,
  ROOMS,
  type RoomId,
  uploadCategories,
} from '../../catalog'

import styles from './UploadModal.module.scss'

/** 올릴 파일 한 줄. */
interface Picked {
  /** 같은 파일을 두 번 골라도 줄이 구분되도록 붙이는 임시 키입니다. */
  key: string
  file: File
}

export interface UploadResult {
  file: File
  category: DocumentCategory
  title: string
  link: DocumentLink
  description: string
}

interface Props {
  /** 올릴 방. 담는 분류와 고를 수 있는 연결이 방마다 다릅니다. */
  room: RoomId
  /** 올리는 중이면 {끝낸 개수, 전체 개수}, 아니면 null 입니다. */
  progress?: { done: number; total: number } | null
  onClose: () => void
  /** 고른 파일 수만큼 한 건씩 넘어옵니다. */
  onSubmit: (results: UploadResult[]) => void
}

/** 확장자를 뗀 파일명. 문서 제목의 기본값입니다. */
const titleOf = (fileName: string) => fileName.replace(/\.[^.]+$/, '')

const pick = (file: File): Picked => ({
  key: `${file.name}-${file.lastModified}-${Math.random().toString(36).slice(2, 8)}`,
  file,
})

export default function UploadModal({ room, progress = null, onClose, onSubmit }: Props) {
  // 파일마다 요청이 오가는 동안 부모의 pending 은 켜졌다 꺼졌다 합니다. 진행 정보가
  // 있는 동안이 곧 올리는 중입니다.
  const submitting = progress !== null
  const fileRef = useRef<HTMLInputElement>(null)
  const { linkKinds } = ROOMS[room]
  // 고를 수 있는 연결이 하나뿐인 방은 고르는 자리를 두지 않고 그것으로 고정합니다.
  const linkFixed = linkKinds.length === 1

  const [picked, setPicked] = useState<Picked[]>([])
  const [dragging, setDragging] = useState(false)
  const [linkKind, setLinkKind] = useState<DocumentLink['kind']>(linkKinds[0])
  // 분류는 연결 대상 하나로 정해지는 값이라 파일 줄마다 두지 않고 한 번만 고릅니다.
  const [category, setCategory] = useState<DocumentCategory>(
    uploadCategories(room, linkKinds[0])[0],
  )
  // 사람이 분류를 한 번이라도 골랐는지. 골랐다면 파일명 추측이 덮지 않습니다.
  const categoryTouched = useRef(false)
  const [linkTarget, setLinkTarget] = useState<RecordOption | null>(null)
  const [description, setDescription] = useState('')

  // 고를 수 있는 분류는 연결 대상에 따라 좁혀집니다.
  const allowed = uploadCategories(room, linkKind)

  // 연결을 바꾸면 고른 분류도 새 목록으로 접습니다. 고를 수 없게 된 분류가 그대로 남아
  // 저장되면 안 됩니다.
  const changeLinkKind = (kind: DocumentLink['kind']) => {
    setLinkKind(kind)
    // 종류가 바뀌면 앞서 고른 것은 다른 목록의 것입니다.
    setLinkTarget(null)
    // 상품 연결은 상품설명서를 쓰는 자리라 분류를 그것으로 맞춰 둡니다.
    setCategory((current) =>
      kind === '상품' ? '상품설명서' : clampCategory(current, uploadCategories(room, kind)),
    )
  }

  const add = (files: FileList | File[]) => {
    const next = Array.from(files).map(pick)
    // 첫 파일을 담을 때만 파일명으로 분류를 찍어 둡니다. 사람이 고른 값은 덮지 않고,
    // 파일명에서 아무것도 읽어 내지 못한 기타로도 덮지 않습니다. 고른 분류가 기타로
    // 튀어 버리는 자리였습니다.
    if (!categoryTouched.current && picked.length === 0 && next.length > 0) {
      const guessed = categoryFromFileName(next[0].file.name, allowed)
      if (guessed) setCategory(guessed)
    }
    setPicked((prev) => [...prev, ...next])
  }

  const submit = () => {
    if (submitting) return
    if (picked.length === 0) {
      showToast('올릴 파일을 고르세요.', { tone: 'error' })
      return
    }
    // 연결 대상을 골랐으면 그 대상은 비울 수 없습니다.
    if (linkKind !== 'none' && linkTarget === null) {
      showToast(`연결할 ${linkKind}을 고르세요.`, { tone: 'error' })
      return
    }
    // 딜이 곧 방 소속인 자료는 딜 없이 올리면 다른 방으로 떨어집니다.
    if (linkTarget === null && needsDeal(room, category)) {
      showToast('기타 자료는 연결할 딜을 고르세요.', { tone: 'error' })
      return
    }

    const link: DocumentLink =
      linkKind === 'none' || linkTarget === null
        ? { kind: 'none', id: '', label: '' }
        : { kind: linkKind, id: linkTarget.id, label: linkTarget.label }

    onSubmit(
      picked.map(({ file }) => ({
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
        <Button type="submit" disabled={submitting}>
          {submitting ? '업로드 중…' : '업로드'}
        </Button>
      }
    >
      {/* 올리는 동안에는 고르는 자리를 걷고 진행만 보여 줍니다. 파일마다 요청이
          오가는 일이라 몇 개째인지가 보여야 멈춘 것으로 읽히지 않습니다. */}
      {progress ? (
        <RecognitionLoading
          title="업로드 중입니다"
          description={`${progress.done}/${progress.total}개 파일을 올리고 AI 요약을 준비하고 있습니다.`}
        />
      ) : (
        <>
          {/* 끌어다 놓기와 고르기 둘 다 됩니다. 브라우저가 파일을 새 탭으로 여는 기본
          동작을 막아야 해서 dragOver 에서도 preventDefault 를 합니다.
          영역 전체가 버튼입니다. div 에 onClick 만 달면 키보드로 닿지 않습니다. */}
          <button
            type="button"
            className={[styles.drop, dragging ? styles.isDragging : ''].filter(Boolean).join(' ')}
            onClick={() => fileRef.current?.click()}
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
            <span className={styles.dropIcon}>
              <UploadIcon width={20} height={20} strokeWidth={1.5} />
            </span>
            <p>파일을 끌어다 놓거나 클릭하세요</p>
            <span className={styles.dropHint}>PDF, DOCX, PPTX, HWP, HTML, TXT, MD</span>
          </button>

          {/* 버튼 안에 두면 잘못된 마크업이라 밖에 둡니다. */}
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

          {picked.length > 0 && (
            <ul className={styles.list}>
              {picked.map((item) => (
                <li key={item.key} className={styles.item}>
                  <div className={styles.file}>
                    <strong className={styles.name}>{item.file.name}</strong>
                    <span className={styles.size}>{sizeLabel(item.file.size)}</span>
                  </div>

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
            {!linkFixed && (
              <Field label="연결 대상" htmlFor={false}>
                <Tabs
                  items={linkKinds.map((kind) => ({
                    value: kind,
                    label: kind === 'none' ? '연결 안 함' : `${kind} 연결`,
                  }))}
                  value={linkKind}
                  label="연결 대상"
                  variant="segmented"
                  className={styles.seg}
                  onChange={changeLinkKind}
                />
              </Field>
            )}

            <Field label="분류" htmlFor={false} wide={linkFixed}>
              <Tabs
                items={allowed.map((item) => ({ value: item, label: item }))}
                value={category}
                label="분류"
                variant="segmented"
                className={styles.seg}
                onChange={(next) => {
                  categoryTouched.current = true
                  setCategory(next)
                }}
              />
            </Field>

            {/* 연결 대상을 고른 뒤에 고르는 칸이라 한 줄을 다 씁니다. */}
            <Field
              label={linkKind === 'none' ? '연결 번호·이름' : linkKind}
              required={linkKind !== 'none'}
              wide
            >
              {linkKind === '상품' ? (
                <RecordPicker<ProductResponse>
                  key={linkKind}
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
                  key={linkKind}
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
              <textarea
                rows={3}
                value={description}
                placeholder="목록에서 이 자료가 무엇인지 알아볼 메모"
                onChange={(event) => setDescription(event.target.value)}
              />
            </Field>
          </div>
        </>
      )}
    </Modal>
  )
}

interface FieldProps {
  label: string
  hint?: string
  required?: boolean
  wide?: boolean
  /** 라디오 묶음처럼 칸 하나를 가리킬 수 없을 때는 label 대신 div 로 감쌉니다. */
  htmlFor?: boolean
  children: React.ReactNode
}

function Field({ label, hint, required, wide, htmlFor = true, children }: FieldProps) {
  const Wrapper = htmlFor ? 'label' : 'div'
  return (
    <Wrapper className={`${styles.field} ${wide ? styles.isWide : ''}`}>
      <span className={styles.label}>
        {label}
        {required && <b aria-hidden="true">*</b>}
        {hint && <i>{hint}</i>}
      </span>
      {children}
    </Wrapper>
  )
}
