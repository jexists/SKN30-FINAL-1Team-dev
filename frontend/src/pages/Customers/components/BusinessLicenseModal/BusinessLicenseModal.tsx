// 사업자등록증 PDF·이미지를 골라 서버 OCR을 실행하고 고객사 등록 폼으로 넘깁니다.
import { useEffect, useRef, useState } from 'react'

import { errorMessage, messageForCode } from '@/api/errorMessage'
import Button from '@/components/Button'
import Modal from '@/components/Modal'
import { ContractIcon, TrashIcon } from '@/components/icons'
import { sizeLabel } from '@/utils/attachment'

import {
  businessLicenseProblem,
  BusinessLicenseScanError,
  BusinessLicenseUnavailableError,
  extractBusinessLicense,
  type BusinessLicenseDraft,
  type LicenseScanProgress,
} from '../../businessLicense'
import RecognitionLoading from '../RecognitionLoading'

import styles from './BusinessLicenseModal.module.scss'

type Phase = 'pick' | 'extracting'

const READ_FALLBACK_MESSAGE = '사업자등록증을 읽지 못했습니다. 잠시 후 다시 시도해 주세요.'

function progressLabel(progress: LicenseScanProgress): string {
  if (progress.phase === 'uploading') return `파일 올리는 중… ${Math.round(progress.percent)}%`
  return `사업자등록증 읽는 중… ${progress.elapsedSeconds}초`
}

interface Props {
  onClose: () => void
  /** OCR 초안은 자동 저장하지 않고 사람이 확인할 고객사 등록 폼으로 넘깁니다. */
  onDrafted: (draft: BusinessLicenseDraft) => void
}

export default function BusinessLicenseModal({ onClose, onDrafted }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [phase, setPhase] = useState<Phase>('pick')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const [progress, setProgress] = useState<LicenseScanProgress | null>(null)

  const reading = phase === 'extracting'

  useEffect(() => {
    if (file === null || !file.type.startsWith('image/')) {
      setPreview(null)
      return
    }
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const pick = (next: File) => {
    const problem = businessLicenseProblem(next)
    if (problem !== null) {
      setError(problem)
      return
    }
    setError(null)
    setUnavailable(false)
    setFile(next)
  }

  const clear = () => {
    setFile(null)
    setError(null)
    setUnavailable(false)
  }

  const read = async () => {
    if (file === null || reading) return

    setPhase('extracting')
    setError(null)
    setUnavailable(false)
    setProgress({ phase: 'uploading', percent: 0 })

    try {
      onDrafted(await extractBusinessLicense(file, setProgress))
    } catch (caught: unknown) {
      if (caught instanceof BusinessLicenseUnavailableError) setUnavailable(true)
      else if (caught instanceof BusinessLicenseScanError) {
        setError(messageForCode(caught.code, READ_FALLBACK_MESSAGE))
      } else setError(errorMessage(caught, READ_FALLBACK_MESSAGE))
      setPhase('pick')
      setProgress(null)
    }
  }

  const close = () => {
    if (!reading) onClose()
  }

  // 읽다 실패한 뒤에도 파일은 그대로 있습니다. 같은 버튼이 다시 읽는 버튼이 됩니다.
  const failed = file !== null && (error !== null || unavailable)

  // 읽는 동안에는 사용자가 손댈 것이 없습니다. 파일 줄과 미리보기, 눌리지 않는 버튼까지
  // 함께 두면 화면만 길어지므로, 어디까지 왔는지 하나만 남깁니다.
  if (reading && progress) {
    return (
      <Modal title="사업자 등록증으로 고객 등록" description="" onClose={close} size="lg">
        <RecognitionLoading description={progressLabel(progress)} />
      </Modal>
    )
  }

  return (
    <Modal
      title="사업자 등록증으로 고객 등록"
      description=""
      onClose={close}
      size="lg"
      footer={
        <Button type="button" disabled={file === null} onClick={read}>
          {failed ? '다시 시도' : '다음'}
        </Button>
      }
    >
      <input
        ref={fileRef}
        data-testid="business-license-file-input"
        type="file"
        accept="application/pdf,image/*,.pdf,.png,.jpg,.jpeg,.webp"
        className="sr-only"
        onChange={(event) => {
          const next = event.target.files?.[0]
          if (next) pick(next)
          event.target.value = ''
        }}
      />

      {file === null ? (
        <>
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
              const dropped = event.dataTransfer.files[0]
              if (dropped) pick(dropped)
            }}
          >
            <ContractIcon width={30} height={30} strokeWidth={1.4} />
            <strong>사업자등록증 PDF 또는 이미지를 업로드하세요</strong>
            <p>PDF·이미지를 여기로 끌어다 놓거나 파일을 선택해 주세요.</p>
            <Button type="button" variant="outline" onClick={() => fileRef.current?.click()}>
              파일 선택
            </Button>
            <span className={styles.limit}>PDF·PNG·JPG·WEBP · 최대 10MB</span>
          </div>

          {error && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}
          {unavailable && (
            <p className={styles.error} role="alert">
              사업자등록증 인식 서버를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.
            </p>
          )}
        </>
      ) : (
        <>
          <div className={styles.picked}>
            <ContractIcon width={22} height={22} strokeWidth={1.5} />
            <span className={styles.file}>
              <strong className={styles.name}>{file.name}</strong>
              <span className={styles.meta}>
                {file.type.startsWith('image/') ? '이미지' : 'PDF'} ·{' '}
                <span className="tnum">{sizeLabel(file.size)}</span>
              </span>
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => fileRef.current?.click()}
            >
              파일 변경
            </Button>
            <button
              type="button"
              className={styles.remove}
              aria-label={`${file.name} 삭제`}
              onClick={clear}
            >
              <TrashIcon />
            </button>
          </div>

          {preview && (
            <img
              className={styles.preview}
              src={preview}
              alt={`선택한 사업자등록증 ${file.name}`}
            />
          )}

          {error && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}
          {unavailable && (
            <p className={styles.error} role="alert">
              사업자등록증 인식 서버를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.
            </p>
          )}
        </>
      )}
    </Modal>
  )
}
