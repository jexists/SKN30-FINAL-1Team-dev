import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

import { errorMessage } from '@/api/errorMessage'
import { downloadReportAttachment } from '@/api/reportAttachments'
import { buttonClass } from '@/components/Button'
import ImageLightbox from '@/components/ImageLightbox'
import Modal from '@/components/Modal'
import { InlineLoader } from '@/components/Skeleton'
import {
  CheckIcon,
  DocumentsIcon,
  FileIcon,
  PlayIcon,
  PlusIcon,
  TrashIcon,
  UploadIcon,
} from '@/components/icons'
import type { AttachmentKind, ReportAttachment } from '@/types'
import { sizeLabel } from '@/utils/attachment'

import AttachmentDrawer from './AttachmentDrawer'
import { EXTRACT_LABEL } from './extractLabel'

import styles from './AttachmentPanel.module.scss'

interface Props {
  attachments: ReportAttachment[]
  /** 읽기 모드면 올리기·녹음·삭제가 사라집니다. */
  readOnly?: boolean
  /** 저장된 보고서의 원본 조회 권한을 확인할 때 씁니다. */
  reportId?: string
  /** 첨부가 그 화면에서 무엇에 쓰이는지. 화면마다 다릅니다. */
  note?: string
  /** 머리를 이 판이 직접 그릴 때의 제목. 없으면 바깥 화면이 제목을 답니다. */
  title?: string
  /** 제목 왼쪽 아이콘. title 과 함께 씁니다. */
  icon?: ReactNode
  /** 아직 아무것도 없을 때 무엇을 넣는 자리인지 말하는 한 줄. */
  description?: string
  /** 놓는 자리 아래 형식·용량 안내. */
  hint?: string
  acceptedKinds?: readonly AttachmentKind[]
  /** 참고자료처럼 이름·용량이 필요 없는 사진 모음. 사진만 깔고 누르면 전체화면으로 엽니다. */
  gallery?: boolean
  onAttach?: (files: FileList | File[], acceptedKinds?: readonly AttachmentKind[]) => void
  onRemove?: (id: string) => void
  /** 미팅 원문에서만 추출된 문장을 교정합니다. 참고자료는 미리보기로 둡니다. */
  onExtractChange?: (id: string, extract: string) => void
}

const KIND_LABEL: Record<AttachmentKind, string> = {
  audio: '음성',
  image: '사진',
  pdf: 'PDF',
}

const ACCEPT: Record<AttachmentKind, string> = {
  audio: '.mp3,.m4a,.wav,.webm',
  image: '.png,.jpg,.jpeg,.webp',
  pdf: '.pdf',
}

export default function AttachmentPanel({
  attachments,
  readOnly = false,
  reportId,
  note = '음성·사진·PDF를 넣으면 초안이 더 자세해집니다. 넣지 않아도 캘린더 일정만으로 작성됩니다.',
  title,
  icon,
  description,
  hint,
  acceptedKinds,
  gallery = false,
  onAttach,
  onRemove,
  onExtractChange,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const panelId = useId()
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set())
  const [preview, setPreview] = useState<{
    reportId: string
    item: ReportAttachment
    url: string
  } | null>(null)
  const [zoom, setZoom] = useState(false)
  /** 갤러리에서 전체화면으로 연 사진. 목록에서 빠지면 조회가 비어 함께 닫힙니다. */
  const [photoId, setPhotoId] = useState<string | null>(null)
  /** 미팅 원문에서 상세를 펼친 파일. 목록에서 빠지면 조회가 비어 드로어도 함께 닫힙니다. */
  const [detailId, setDetailId] = useState<string | null>(null)
  /**
   * 저장된 보고서에서 서버로부터 받아 온 원본 주소. null 은 받는 중, false 는 실패입니다.
   * 실패도 자리를 남겨 둡니다 — 지우면 갤러리 효과가 다시 불러 끝없이 되풉니다.
   * 올린 그 자리에서는 previewUrl 이 이미 있어 여기까지 오지 않습니다.
   */
  const [origins, setOrigins] = useState<Record<string, string | null | false>>({})
  const [loadingFile, setLoadingFile] = useState<{ reportId: string; id: string } | null>(null)
  const [fileError, setFileError] = useState<{ reportId: string; message: string } | null>(null)
  const requestRef = useRef<AbortController | null>(null)
  const objectUrls = useRef(new Set<string>())

  useEffect(
    () => () => {
      requestRef.current?.abort()
      requestRef.current = null
      objectUrls.current.forEach((url) => URL.revokeObjectURL(url))
      objectUrls.current.clear()
      setOrigins({})
    },
    [reportId],
  )

  const closePreview = () => {
    if (preview) {
      URL.revokeObjectURL(preview.url)
      objectUrls.current.delete(preview.url)
    }
    // 전체보기가 이 주소를 그대로 씁니다. 주소를 거두기 전에 함께 내립니다.
    setZoom(false)
    setPreview(null)
  }

  const openOriginal = async (item: ReportAttachment, download = false) => {
    if (!reportId) return
    requestRef.current?.abort()
    const controller = new AbortController()
    requestRef.current = controller
    setLoadingFile({ reportId, id: item.id })
    setFileError(null)
    closePreview()
    try {
      const blob = await downloadReportAttachment(reportId, item.id, controller.signal)
      if (controller.signal.aborted) return
      const url = URL.createObjectURL(blob)
      objectUrls.current.add(url)
      if (download) {
        const link = document.createElement('a')
        link.href = url
        link.download = item.name
        link.click()
        window.setTimeout(() => {
          URL.revokeObjectURL(url)
          objectUrls.current.delete(url)
        }, 1_000)
      } else {
        setPreview({ reportId, item, url })
      }
    } catch (reason: unknown) {
      if (!controller.signal.aborted) {
        setFileError({
          reportId,
          message: errorMessage(reason, '첨부 원본을 불러오지 못했습니다. 다시 시도해 주세요.'),
        })
      }
    } finally {
      if (!controller.signal.aborted) setLoadingFile(null)
    }
  }

  /**
   * 저장된 보고서의 원본을 받아 주소를 잡아 둡니다. previewUrl 은 올린 그 자리에서만 사는 주소라
   * 새로 연 화면에는 없습니다. openOriginal 의 단일 abort 는 쓰지 않습니다 — 갤러리는 여러 장을
   * 한꺼번에 부르므로 서로를 취소해 버립니다. 실패는 삼키고 드로어가 대신 말합니다.
   */
  const ensureOrigin = async (item: ReportAttachment) => {
    if (!reportId || !item.originalStored || item.previewUrl || item.id in origins) return
    setOrigins((prev) => ({ ...prev, [item.id]: null }))
    try {
      const blob = await downloadReportAttachment(reportId, item.id)
      const url = URL.createObjectURL(blob)
      objectUrls.current.add(url)
      setOrigins((prev) => ({ ...prev, [item.id]: url }))
    } catch {
      setOrigins((prev) => ({ ...prev, [item.id]: false }))
    }
  }

  /** 얼굴·전체화면·드로어가 함께 보는 원본 주소. */
  const srcOf = (item: ReportAttachment) => item.previewUrl || origins[item.id] || undefined

  // 갤러리는 사진이 곧 목록입니다. 누르기 전에 깔려 있어야 하므로 미리 받아 둡니다.
  // 줄 목록은 누를 때만 받습니다 — 녹음·PDF 는 눌리지도 않은 채 통째로 내려받을 것이 아닙니다.
  useEffect(() => {
    if (!gallery) return
    attachments
      .filter((item) => item.kind === 'image')
      .forEach((item) => {
        void ensureOrigin(item)
      })
    // ensureOrigin 은 origins 를 닫고 있어 매 렌더 새로 만들어집니다. 이미 받은 것은
    // 그 안에서 걸러지므로, 의존은 목록과 받은 결과만 봅니다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gallery, attachments, origins, reportId])

  const toggleExtract = (id: string) => {
    setOpen((prev) => {
      const next = new Set(prev)
      if (!next.delete(id)) next.add(id)
      return next
    })
  }

  const openPicker = () => fileRef.current?.click()

  // 머리에 올린 버튼이 놓는 자리를 대신합니다. 머리가 없는 화면은 놓는 자리를 그대로 둡니다.
  const headAdd = Boolean(title) && !readOnly && attachments.length > 0
  const showDropzone = !readOnly && !headAdd
  const audioItems = attachments.filter((item) => item.kind === 'audio')
  const fileItems = attachments.filter((item) => item.kind !== 'audio')
  /**
   * 목록과 상세를 나눕니다. 목록은 한 줄로 훑고, 원본 확인·교정은 드로어가 맡습니다.
   * 잠긴 미팅 화면도, 낸 뒤의 상세 화면도 같은 목록입니다 — 읽기 전용이 되는 것이지
   * 다른 화면이 되는 것이 아닙니다. reportId 없이 잠기기만 하는 일일 참고자료는
   * 종류가 섞여 있어 지금까지의 카드·타일 그대로 둡니다.
   */
  const galleryMode = gallery
  const rows = !galleryMode && (Boolean(onExtractChange) || (readOnly && Boolean(reportId)))
  const detailItem = attachments.find((item) => item.id === detailId) ?? null
  const photoItem = attachments.find((item) => item.id === photoId) ?? null

  const loading = (item: ReportAttachment) =>
    loadingFile?.reportId === reportId && loadingFile?.id === item.id
  const extractable = (item: ReportAttachment) =>
    item.state === 'done' && Boolean(item.extract || onExtractChange)
  /** 원문 화면은 교정할 추출 원문, 참고자료는 정리된 내용입니다. */
  const extractWord = onExtractChange ? '원문' : '내용'

  /** 파일 얼굴. 사진은 올린 그림 그대로, 나머지는 종류 아이콘입니다. */
  const face = (item: ReportAttachment) =>
    item.kind === 'image' && srcOf(item) ? (
      <img className={styles.thumbImage} src={srcOf(item)} alt="" />
    ) : item.kind === 'audio' ? (
      <PlayIcon width={20} height={20} />
    ) : item.kind === 'pdf' ? (
      <FileIcon width={20} height={20} />
    ) : (
      <DocumentsIcon width={20} height={20} />
    )

  const thumb = (item: ReportAttachment, className: string) => (
    <span className={className} aria-hidden="true">
      {face(item)}
    </span>
  )

  const meta = (item: ReportAttachment) => (
    <span className={styles.meta} role={item.state === 'analyzing' ? 'status' : undefined}>
      {sizeLabel(item.byteSize)}
      {item.state === 'analyzing' && ' · 업로드·분석 중…'}
      {item.state === 'failed' && ' · 업로드·분석 실패'}
      {item.state === 'done' && Boolean(item.extract) && (
        <>
          {/* 가운뎃점은 inline-flex 바깥에 둡니다. 안에 넣으면 앞뒤 공백이 잘려 '3.1MB·✓' 로 붙습니다. */}
          {' · '}
          <span className={styles.done}>
            <CheckIcon width={12} height={12} />
            {EXTRACT_LABEL[item.kind]} 완료
          </span>
        </>
      )}
    </span>
  )

  const notice = (item: ReportAttachment) =>
    !readOnly ? null : item.originalStored && reportId ? (
      <div className={styles.fileActions}>
        <button
          type="button"
          className={styles.toggle}
          disabled={loading(item)}
          onClick={() => void openOriginal(item)}
        >
          원본 보기
        </button>
        <button
          type="button"
          className={styles.toggle}
          disabled={loading(item)}
          onClick={() => void openOriginal(item, true)}
        >
          다운로드
        </button>
        {loading(item) && (
          <span className={styles.meta} role="status">
            원본 불러오는 중…
          </span>
        )}
      </div>
    ) : !item.originalStored ? (
      <span className={styles.meta}>원본 파일이 저장되지 않아 확인할 수 없습니다.</span>
    ) : null

  const removeButton = (item: ReportAttachment) =>
    readOnly ? null : (
      <button
        type="button"
        className={styles.remove}
        aria-label={`${item.name} ${item.state === 'analyzing' ? '업로드 취소' : '삭제'}`}
        onClick={() => onRemove?.(item.id)}
      >
        <TrashIcon />
      </button>
    )

  const toggleButton = (item: ReportAttachment, label: string) => (
    <button
      type="button"
      className={styles.toggle}
      aria-expanded={open.has(item.id)}
      aria-controls={`${panelId}-${item.id}-extract`}
      onClick={() => toggleExtract(item.id)}
    >
      {label} {open.has(item.id) ? '접기' : '보기'}
    </button>
  )

  /** 펼친 추출 원문. 원문 화면에서는 교정칸이고 그 밖에는 읽기용입니다. */
  const extractPanel = (item: ReportAttachment) =>
    onExtractChange && !readOnly ? (
      <div key={item.id} className={styles.editor}>
        <label htmlFor={`${panelId}-${item.id}-extract`}>{item.name} 추출 원문 확인·수정</label>
        <textarea
          id={`${panelId}-${item.id}-extract`}
          aria-label={`${item.name} 추출 원문 확인·수정`}
          rows={5}
          value={item.extract ?? ''}
          onChange={(event) => onExtractChange(item.id, event.target.value)}
        />
      </div>
    ) : (
      <p key={item.id} id={`${panelId}-${item.id}-extract`} className={styles.extract}>
        {item.extract}
      </p>
    )

  return (
    <div className={styles.root} aria-busy={attachments.some((item) => item.state === 'analyzing')}>
      {title && (
        <div className={styles.head}>
          {icon}
          <strong>{title}</strong>
          {headAdd && (
            <button type="button" className={styles.addBtn} onClick={openPicker}>
              <PlusIcon width={14} height={14} />
              파일 추가
            </button>
          )}
        </div>
      )}

      {!readOnly && (
        <>
          {/* 갤러리는 사진만 깔려 이름이 없으니, 무엇을 넣는 자리인지는 설명이 계속 말합니다. */}
          {description && (gallery || attachments.length === 0) && (
            <p className={styles.description}>{description}</p>
          )}
          {note && <p className={styles.note}>{note}</p>}

          {/*
           * 파일을 넣는 자리는 버튼이 아니라 면입니다. 빈 칸에 작은 버튼 하나만 얹으면
           * 남은 자리가 무엇에 쓰는 곳인지 말하지 않습니다 — 자리 전체가 그 말을 합니다.
           */}
          {showDropzone && (
            <button type="button" className={styles.dropzone} onClick={openPicker}>
              <span className={styles.dropLabel}>
                <UploadIcon />
                파일 추가
              </span>
              {hint && <span className={styles.dropHint}>{hint}</span>}
            </button>
          )}

          {/* 기본 파일 입력은 스타일을 맞출 수 없어 숨기고 버튼으로 엽니다. */}
          <input
            ref={fileRef}
            type="file"
            multiple
            accept={
              acceptedKinds
                ? acceptedKinds.map((kind) => ACCEPT[kind]).join(',')
                : Object.values(ACCEPT).join(',')
            }
            aria-label={
              acceptedKinds
                ? `${acceptedKinds.map((kind) => KIND_LABEL[kind]).join('·')} 첨부 파일 선택`
                : '첨부 파일 선택'
            }
            tabIndex={-1}
            className="sr-only"
            onChange={(event) => {
              if (event.target.files) onAttach?.(event.target.files, acceptedKinds)
              // 같은 파일을 다시 골라도 change 가 나게 비웁니다.
              event.target.value = ''
            }}
          />
        </>
      )}

      {/* 작성 화면에서는 빈 상태를 말하지 않습니다. 바로 위 '파일 추가'가 그 자리를 설명합니다. */}
      {attachments.length === 0 && readOnly && <p className={styles.empty}>첨부 없음</p>}

      {/*
       * 미팅 원문 목록. 한 줄에 파일 얼굴·이름·상태·추출문 맛보기까지만 싣고, 누르면 드로어가 엽니다.
       * 삭제는 줄 버튼 안이 아니라 형제로 둡니다 — 버튼 안의 버튼을 만들지 않으면
       * 클릭이 새는 일도 없습니다.
       */}
      {rows && attachments.length > 0 && (
        <ul className={styles.list} data-readonly={readOnly || undefined}>
          {attachments.map((item) => (
            <li key={item.id} className={styles.listItem}>
              <button
                type="button"
                className={styles.row}
                disabled={item.state !== 'done'}
                onClick={() => {
                  setDetailId(item.id)
                  void ensureOrigin(item)
                }}
              >
                {thumb(item, styles.thumb)}
                <span className={styles.rowBody}>
                  <span className={styles.name}>{item.name}</span>
                  {meta(item)}
                  {Boolean(item.extract) && (
                    <span className={styles.rowPreview}>{item.extract}</span>
                  )}
                </span>
              </button>
              {removeButton(item)}
            </li>
          ))}
        </ul>
      )}

      {/* 참고자료 갤러리. 이름도 용량도 없이 사진만, 누르면 전체화면입니다. */}
      {galleryMode && attachments.length > 0 && (
        <ul className={styles.gallery}>
          {attachments.map((item) => (
            <li key={item.id} className={styles.photoItem}>
              <button
                type="button"
                className={styles.photo}
                data-state={item.state}
                disabled={item.state !== 'done' || !srcOf(item)}
                aria-label={`${item.name} 크게 보기`}
                onClick={() => setPhotoId(item.id)}
              >
                {srcOf(item) ? (
                  <img className={styles.thumbImage} src={srcOf(item)} alt="" />
                ) : (
                  <DocumentsIcon width={20} height={20} />
                )}
              </button>
              {/* 올리는 동안은 사진 위에서 아이콘만 돕니다. 실패는 테두리가 빨갛게 말합니다. */}
              {item.state === 'analyzing' && (
                <InlineLoader className={styles.photoLoading} label={`${item.name} 올리는 중`} />
              )}
              {removeButton(item)}
            </li>
          ))}
        </ul>
      )}

      {!galleryMode && !rows && audioItems.length > 0 && (
        <ul className={styles.cards}>
          {audioItems.map((item) => (
            <li key={item.id} className={styles.card}>
              <div className={styles.cardRow}>
                {thumb(item, styles.thumb)}
                <div className={styles.body}>
                  <strong className={styles.name}>{item.name}</strong>
                  {meta(item)}
                  {notice(item)}
                </div>
                {removeButton(item)}
              </div>

              {extractable(item) && (
                <div className={styles.extractBar}>
                  <span>{onExtractChange ? '추출 원문' : '정리된 내용'}</span>
                  {toggleButton(item, extractWord)}
                </div>
              )}
              {extractable(item) && open.has(item.id) && extractPanel(item)}
            </li>
          ))}
        </ul>
      )}

      {!galleryMode && !rows && fileItems.length > 0 && (
        <>
          <ul className={styles.tiles}>
            {fileItems.map((item) => (
              <li key={item.id} className={styles.tile}>
                {thumb(item, styles.tileFace)}
                <div className={styles.tileBody}>
                  <strong className={styles.name}>{item.name}</strong>
                  {meta(item)}
                  {notice(item)}
                  {extractable(item) && toggleButton(item, extractWord)}
                </div>
                {removeButton(item)}
              </li>
            ))}
          </ul>
          {/* 타일은 좁아서 원문을 안에 담지 못합니다. 펼친 것만 그리드 아래 폭 전체로 폅니다. */}
          {fileItems.filter((item) => extractable(item) && open.has(item.id)).map(extractPanel)}
        </>
      )}

      {/* 왼쪽 자료 열은 스크롤 상자(sticky + overflow) 안이라, 그 안에서 서랍을 열면
          화면 전체를 덮어야 할 배경이 열 안에 갇힙니다. 미리보기와 같이 body 로 옮깁니다. */}
      {detailItem &&
        createPortal(
          <AttachmentDrawer
            item={detailItem}
            readOnly={readOnly}
            originalUrl={srcOf(detailItem)}
            originalPending={origins[detailItem.id] === null}
            onDownload={
              reportId && detailItem.originalStored
                ? () => void openOriginal(detailItem, true)
                : undefined
            }
            onExtractChange={onExtractChange}
            onClose={() => setDetailId(null)}
          />,
          document.body,
        )}

      {fileError && fileError.reportId === reportId && (
        <p className={styles.error} role="alert">
          {fileError.message}
        </p>
      )}
      {preview &&
        preview.reportId === reportId &&
        createPortal(
          <div
            className={styles.previewHost}
            onPointerDown={(event) => event.stopPropagation()}
            onKeyDownCapture={(event) => {
              if (event.key === 'Escape') {
                event.stopPropagation()
                closePreview()
              }
            }}
          >
            <Modal
              title={preview.item.name}
              size="lg"
              onClose={closePreview}
              footer={
                <a className={buttonClass()} href={preview.url} download={preview.item.name}>
                  다운로드
                </a>
              }
            >
              <div tabIndex={0} role="group" aria-label="원본 파일 미리보기">
                {preview.item.kind === 'image' ? (
                  /* 모달 폭에 맞춰 줄여 놓은 사진입니다. 글자가 작으면 눌러서 전체보기로 엽니다. */
                  <button
                    type="button"
                    className={styles.previewZoom}
                    aria-label={`${preview.item.name} 크게 보기`}
                    onClick={() => setZoom(true)}
                  >
                    <img
                      className={styles.previewImage}
                      src={preview.url}
                      alt={preview.item.name}
                    />
                  </button>
                ) : preview.item.kind === 'audio' ? (
                  <audio className={styles.previewAudio} src={preview.url} controls />
                ) : (
                  <iframe
                    className={styles.previewPdf}
                    src={preview.url}
                    title={preview.item.name}
                  />
                )}
              </div>
            </Modal>
          </div>,
          document.body,
        )}
      {/* previewHost 바깥에 둡니다. 안에 두면 그 div 의 Escape 캡처 핸들러가 먼저 잡아
          전체보기만 닫으려 한 것이 미리보기 모달까지 닫습니다. */}
      {photoItem && srcOf(photoItem) && (
        <ImageLightbox
          src={srcOf(photoItem) as string}
          alt={photoItem.name}
          caption={photoItem.name}
          onClose={() => setPhotoId(null)}
        />
      )}
      {preview && preview.reportId === reportId && zoom && (
        <ImageLightbox
          src={preview.url}
          alt={preview.item.name}
          caption={`${preview.item.name} · ${sizeLabel(preview.item.byteSize)}`}
          onClose={() => setZoom(false)}
        />
      )}
    </div>
  )
}
