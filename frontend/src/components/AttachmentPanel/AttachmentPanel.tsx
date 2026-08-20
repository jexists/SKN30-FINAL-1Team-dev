import { useRef, useState } from 'react'

import { TrashIcon, UploadIcon } from '@/components/icons'
import type { AttachmentKind, ReportAttachment } from '@/types'

import styles from './AttachmentPanel.module.scss'

interface Props {
  attachments: ReportAttachment[]
  /** 읽기 모드면 올리기·녹음·삭제가 사라집니다. */
  readOnly?: boolean
  /** 첨부가 그 화면에서 무엇에 쓰이는지. 화면마다 다릅니다. */
  note?: string
  onAttach?: (files: FileList | File[]) => void
  onRemove?: (id: string) => void
}

const KIND_LABEL: Record<AttachmentKind, string> = {
  audio: '음성',
  image: '사진',
  pdf: 'PDF',
}

export default function AttachmentPanel({
  attachments,
  readOnly = false,
  note = '음성·사진·PDF를 넣으면 초안이 더 자세해집니다. 넣지 않아도 캘린더 일정만으로 작성됩니다.',
  onAttach,
  onRemove,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set())

  const toggleExtract = (id: string) => {
    setOpen((prev) => {
      const next = new Set(prev)
      if (!next.delete(id)) next.add(id)
      return next
    })
  }

  return (
    <div>
      {!readOnly && (
        <>
          <p className={styles.note}>{note}</p>

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
              accept="audio/*,image/*,application/pdf"
              className="sr-only"
              onChange={(event) => {
                if (event.target.files) onAttach?.(event.target.files)
                // 같은 파일을 다시 골라도 change 가 나게 비웁니다.
                event.target.value = ''
              }}
            />
          </div>
        </>
      )}

      {attachments.length === 0 ? (
        <p className={styles.empty}>{readOnly ? '첨부 없음' : '첨부한 자료가 없습니다.'}</p>
      ) : (
        <ul className={styles.list}>
          {attachments.map((item) => (
            <li key={item.id} className={styles.item}>
              <span className={styles.kind}>{KIND_LABEL[item.kind]}</span>

              <div className={styles.body}>
                <strong className={styles.name}>{item.name}</strong>
                <span className={styles.meta}>
                  {item.size}
                  {item.state === 'analyzing' && ' · 분석 중…'}
                  {item.state === 'failed' && ' · 분석 실패'}
                </span>

                {item.state === 'done' && item.extract && (
                  <>
                    <button
                      type="button"
                      className={styles.toggle}
                      aria-expanded={open.has(item.id)}
                      onClick={() => toggleExtract(item.id)}
                    >
                      분석 완료 · 정리된 내용 {open.has(item.id) ? '접기' : '보기'}
                    </button>
                    {open.has(item.id) && <p className={styles.extract}>{item.extract}</p>}
                  </>
                )}
              </div>

              {!readOnly && (
                <button
                  type="button"
                  className={styles.remove}
                  aria-label={`${item.name} 삭제`}
                  onClick={() => onRemove?.(item.id)}
                >
                  <TrashIcon />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
