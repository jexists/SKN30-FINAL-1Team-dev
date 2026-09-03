// 사업자등록증 PDF 로 고객을 넣는 화면입니다. 여기서 하는 일은 PDF 를 고르는 것뿐입니다.
//
// 읽어 낸 값은 여기서 저장하지도, 다시 확인받지도 않습니다. 명함과 같은 방식으로 등록 폼에
// 넘겨, 사람이 담당자 이름까지 채우고 한 번에 등록합니다. 새 API 없이 기존 등록 길을 탑니다.
import { useRef, useState } from 'react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import ProgressBar from '@/components/ProgressBar'
import { ContractIcon, TrashIcon } from '@/components/icons'
import { sizeLabel } from '@/utils/attachment'

import {
  extractBusinessLicense,
  pdfProblem,
  type BusinessLicenseDraft,
} from '../../businessLicense'

import styles from './BusinessLicenseModal.module.scss'

/** 지금 어느 단계인지. 읽는 동안에는 고르기 칸이 잠깁니다. */
type Phase = 'pick' | 'extracting'

const READ_FALLBACK_MESSAGE = '사업자등록증을 읽지 못했습니다. 잠시 후 다시 시도해 주세요.'

interface Props {
  onClose: () => void
  /** 등록증에서 읽어 낸 값. 부른 쪽이 등록 폼에 채워 넣습니다. */
  onDrafted: (draft: BusinessLicenseDraft) => void
}

export default function BusinessLicenseModal({ onClose, onDrafted }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)

  const [phase, setPhase] = useState<Phase>('pick')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reading = phase === 'extracting'

  const pick = (next: File) => {
    const problem = pdfProblem(next)
    if (problem !== null) {
      setError(problem)
      return
    }
    setError(null)
    setFile(next)
  }

  const clear = () => {
    setFile(null)
    setError(null)
  }

  const read = async () => {
    if (file === null || reading) return

    setPhase('extracting')
    setError(null)

    try {
      // 부른 쪽이 이 모달을 등록 폼으로 갈아 끼웁니다. 뒷정리는 필요 없습니다.
      onDrafted(await extractBusinessLicense(file))
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : READ_FALLBACK_MESSAGE)
      setPhase('pick')
    }
  }

  const close = () => {
    if (!reading) onClose()
  }

  return (
    <Modal
      title="사업자 등록증으로 고객 등록"
      description="사업자등록증 PDF를 업로드하면 읽어 낸 값이 고객 등록 폼에 채워집니다."
      onClose={close}
      footer={
        <>
          <Button type="button" variant="outline" disabled={reading} onClick={close}>
            취소
          </Button>
          <Button type="button" disabled={file === null || reading} onClick={read}>
            {reading ? '읽는 중…' : '다음'}
          </Button>
        </>
      }
    >
      <input
        ref={fileRef}
        data-testid="business-license-pdf-input"
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        onChange={(event) => {
          const next = event.target.files?.[0]
          if (next) pick(next)
          // 같은 파일을 다시 골라도 change 가 나게 비웁니다.
          event.target.value = ''
        }}
      />

      {file === null ? (
        <>
          {/* 끌어다 놓기와 고르기 둘 다 됩니다. 브라우저가 PDF 를 새 탭으로 여는 기본
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
              const dropped = event.dataTransfer.files[0]
              if (dropped) pick(dropped)
            }}
          >
            <ContractIcon width={30} height={30} strokeWidth={1.4} />
            <strong>사업자등록증 PDF를 업로드하세요</strong>
            <p>PDF 파일을 여기로 끌어다 놓거나 파일을 선택해 주세요.</p>
            <Button type="button" variant="outline" onClick={() => fileRef.current?.click()}>
              파일 선택
            </Button>
            <span className={styles.limit}>PDF 파일만 올릴 수 있습니다 · 최대 10MB</span>
          </div>

          {error && (
            <p className={styles.error} role="alert">
              {error}
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
                PDF · <span className="tnum">{sizeLabel(file.size)}</span>
              </span>
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={reading}
              onClick={() => fileRef.current?.click()}
            >
              파일 변경
            </Button>
            <button
              type="button"
              className={styles.remove}
              aria-label={`${file.name} 삭제`}
              disabled={reading}
              onClick={clear}
            >
              <TrashIcon />
            </button>
          </div>

          {reading && (
            <div className={styles.progress}>
              <ProgressBar label="사업자등록증을 읽는 중입니다." />
              <p className={styles.step}>사업자등록증을 읽는 중…</p>
            </div>
          )}

          {error && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}
        </>
      )}
    </Modal>
  )
}
