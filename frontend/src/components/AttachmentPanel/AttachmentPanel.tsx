import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { errorMessage } from '@/api/errorMessage'
import { downloadReportAttachment } from '@/api/reportAttachments'
import { buttonClass } from '@/components/Button'
import ImageLightbox from '@/components/ImageLightbox'
import Modal from '@/components/Modal'
import { TrashIcon, UploadIcon } from '@/components/icons'
import type { AttachmentKind, ReportAttachment } from '@/types'
import { sizeLabel } from '@/utils/attachment'

import styles from './AttachmentPanel.module.scss'

interface Props {
  attachments: ReportAttachment[]
  /** 읽기 모드면 올리기·녹음·삭제가 사라집니다. */
  readOnly?: boolean
  /** 저장된 보고서의 원본 조회 권한을 확인할 때 씁니다. */
  reportId?: string
  /** 첨부가 그 화면에서 무엇에 쓰이는지. 화면마다 다릅니다. */
  note?: string
  acceptedKinds?: readonly AttachmentKind[]
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
  acceptedKinds,
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

  const toggleExtract = (id: string) => {
    setOpen((prev) => {
      const next = new Set(prev)
      if (!next.delete(id)) next.add(id)
      return next
    })
  }

  return (
    <div aria-busy={attachments.some((item) => item.state === 'analyzing')}>
      {!readOnly && (
        <>
          {note && <p className={styles.note}>{note}</p>}

          <div className={styles.actions}>
            <button
              type="button"
              className={styles.action}
              onClick={() => fileRef.current?.click()}
            >
              <UploadIcon />
              파일 추가
            </button>

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
          </div>
        </>
      )}

      {/* 작성 화면에서는 빈 상태를 말하지 않습니다. 바로 위 '파일 추가'가 그 자리를 설명합니다. */}
      {attachments.length === 0 ? (
        readOnly && <p className={styles.empty}>첨부 없음</p>
      ) : (
        <ul className={styles.list}>
          {attachments.map((item) => (
            <li key={item.id} className={styles.item}>
              <span className={styles.kind}>{KIND_LABEL[item.kind]}</span>

              <div className={styles.body}>
                <strong className={styles.name}>{item.name}</strong>
                <span
                  className={styles.meta}
                  role={item.state === 'analyzing' ? 'status' : undefined}
                >
                  {sizeLabel(item.byteSize)}
                  {item.state === 'analyzing' && ' · 업로드·분석 중…'}
                  {item.state === 'failed' && ' · 업로드·분석 실패'}
                </span>

                {readOnly &&
                  (item.originalStored && reportId ? (
                    <div className={styles.fileActions}>
                      <button
                        type="button"
                        className={styles.toggle}
                        disabled={loadingFile?.reportId === reportId && loadingFile.id === item.id}
                        onClick={() => void openOriginal(item)}
                      >
                        원본 보기
                      </button>
                      <button
                        type="button"
                        className={styles.toggle}
                        disabled={loadingFile?.reportId === reportId && loadingFile.id === item.id}
                        onClick={() => void openOriginal(item, true)}
                      >
                        다운로드
                      </button>
                      {loadingFile?.reportId === reportId && loadingFile.id === item.id && (
                        <span className={styles.meta} role="status">
                          원본 불러오는 중…
                        </span>
                      )}
                    </div>
                  ) : !item.originalStored ? (
                    <span className={styles.meta}>
                      원본 파일이 저장되지 않아 확인할 수 없습니다.
                    </span>
                  ) : null)}

                {item.state === 'done' && (item.extract || onExtractChange) && (
                  <>
                    <button
                      type="button"
                      className={styles.toggle}
                      aria-expanded={open.has(item.id)}
                      aria-controls={`${panelId}-${item.id}-extract`}
                      onClick={() => toggleExtract(item.id)}
                    >
                      {onExtractChange
                        ? `${item.kind === 'audio' ? 'STT' : item.kind === 'image' ? 'OCR' : '텍스트 추출'} 완료 · 원문`
                        : '분석 완료 · 정리된 내용'}{' '}
                      {open.has(item.id) ? '접기' : '보기'}
                    </button>
                    {open.has(item.id) &&
                      (onExtractChange && !readOnly ? (
                        <div className={styles.editor}>
                          <label htmlFor={`${panelId}-${item.id}-extract`}>
                            추출 원문 확인·수정
                          </label>
                          <textarea
                            id={`${panelId}-${item.id}-extract`}
                            aria-label={`${item.name} 추출 원문 확인·수정`}
                            rows={5}
                            value={item.extract ?? ''}
                            onChange={(event) => onExtractChange(item.id, event.target.value)}
                          />
                        </div>
                      ) : (
                        <p id={`${panelId}-${item.id}-extract`} className={styles.extract}>
                          {item.extract}
                        </p>
                      ))}
                  </>
                )}
              </div>

              {!readOnly && (
                <button
                  type="button"
                  className={styles.remove}
                  aria-label={`${item.name} ${item.state === 'analyzing' ? '업로드 취소' : '삭제'}`}
                  onClick={() => onRemove?.(item.id)}
                >
                  <TrashIcon />
                </button>
              )}
            </li>
          ))}
        </ul>
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
