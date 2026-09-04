import { useEffect, useRef, useState } from 'react'

import { errorMessage, messageForCode } from '@/api/errorMessage'
import Button from '@/components/Button'
import { CardIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import { sizeLabel } from '@/utils/attachment'

import {
  BusinessCardScanError,
  BusinessCardUnavailableError,
  MAX_IMAGE_BYTES,
  recognizeBusinessCard,
  type BusinessCardDraft,
  type ScanProgress,
} from '../../businessCard'
import RecognitionLoading from '../RecognitionLoading'

import styles from './BusinessCardModal.module.scss'

const SCAN_FALLBACK_MESSAGE = '명함을 읽지 못했습니다. 사진이 흐리면 다시 찍어 주세요.'

/** 지금 어느 단계인지 한 줄로 말합니다. 진행 막대만으로는 무엇을 기다리는지 모릅니다. */
function progressLabel(progress: ScanProgress): string {
  if (progress.phase === 'resizing') return '사진 준비 중…'
  if (progress.phase === 'uploading') return `사진 올리는 중… ${Math.round(progress.percent)}%`
  return `명함 읽는 중… ${progress.elapsedSeconds}초`
}

interface BusinessCardModalProps {
  onClose: () => void
  /** 읽어 낸 값. 사람이 확인하고 고칠 수 있게 등록 폼으로 넘깁니다. */
  onRecognized: (draft: BusinessCardDraft) => void
  /** 인식을 건너뛰고 빈 등록 폼으로 갑니다. */
  onManual: () => void
}

export default function BusinessCardModal({
  onClose,
  onRecognized,
  onManual,
}: BusinessCardModalProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [image, setImage] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const [reading, setReading] = useState(false)
  const [progress, setProgress] = useState<ScanProgress | null>(null)

  // 미리보기 주소는 붙잡고 있으면 사진이 메모리에 그대로 남습니다.
  useEffect(() => {
    if (image === null) {
      setPreview(null)
      return
    }
    const url = URL.createObjectURL(image)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [image])

  const pick = (file: File) => {
    setError(null)
    setUnavailable(false)

    if (!file.type.startsWith('image/')) {
      setError('명함을 찍은 사진을 넣어 주세요. 이미지 파일만 읽습니다.')
      return
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setError(
        `사진이 ${sizeLabel(file.size)} 입니다. ${sizeLabel(MAX_IMAGE_BYTES)} 까지 넣을 수 있습니다.`,
      )
      return
    }
    setImage(file)
  }

  const read = async () => {
    if (image === null || reading) return

    setReading(true)
    setError(null)
    setUnavailable(false)
    setProgress({ phase: 'resizing' })

    try {
      onRecognized(await recognizeBusinessCard(image, setProgress))
    } catch (caught: unknown) {
      // 어디서 실패했는지 말해 줍니다. 업로드가 끊긴 경우까지 "사진이 흐리다" 로
      // 안내하면 사용자가 고칠 수 없는 것을 고치려 합니다.
      if (caught instanceof BusinessCardUnavailableError) setUnavailable(true)
      else if (caught instanceof BusinessCardScanError)
        setError(messageForCode(caught.code, SCAN_FALLBACK_MESSAGE))
      // 업로드 검증 실패처럼 서버가 코드를 실어 보낸 응답은 그 문구를 그대로 씁니다.
      else setError(errorMessage(caught, SCAN_FALLBACK_MESSAGE))
      setReading(false)
      setProgress(null)
    }
  }

  const close = () => {
    if (!reading) onClose()
  }

  return (
    <Modal
      title="명함으로 고객 등록"
      description=""
      onClose={close}
      footer={
        <>
          <Button type="button" variant="outline" disabled={reading} onClick={close}>
            취소
          </Button>
          <Button type="button" disabled={image === null || reading} onClick={read}>
            {reading ? '읽는 중…' : '명함 읽기'}
          </Button>
        </>
      }
    >
      <input
        ref={fileRef}
        data-testid="business-card-image-input"
        type="file"
        accept="image/*"
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) pick(file)
          event.target.value = ''
        }}
      />

      {/* 명함 비율(91×55) 그대로입니다. 무엇을 넣는 자리인지 글자보다 먼저 보입니다. */}
      <button
        type="button"
        className={styles.drop}
        disabled={reading}
        onClick={() => fileRef.current?.click()}
      >
        {preview === null ? (
          <span className={styles.empty}>
            <CardIcon width={30} height={30} strokeWidth={1.4} />
            <strong>명함 사진 선택</strong>
            <span>화면에 꽉 차게, 글자가 또렷하게 찍어 주세요.</span>
          </span>
        ) : (
          <img
            className={styles.shot}
            src={preview}
            alt={`선택한 명함 사진 ${image?.name ?? ''}`}
          />
        )}
      </button>

      {image && (
        <p className={styles.file}>
          {image.name} · <span className="tnum">{sizeLabel(image.size)}</span> · 다시 고르려면
          사진을 누르세요.
        </p>
      )}

      {reading && progress && (
        <RecognitionLoading
          description={progressLabel(progress)}
          progress={progress.phase === 'uploading' ? progress.percent : undefined}
        />
      )}

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {unavailable && (
        <div className={styles.notice} role="alert">
          <p>
            OCR 서버를 사용할 수 없습니다. 지금은 등록 폼에 직접 입력하거나 잠시 후 다시 시도해
            주세요.
          </p>
          <Button type="button" variant="outline" size="sm" onClick={onManual}>
            직접 입력으로 등록
          </Button>
        </div>
      )}
    </Modal>
  )
}
