import { useId } from 'react'

import type { MeetingProgress, MeetingSharedNotes } from '@/types'

import styles from './MeetingSharedPanel.module.scss'
import GenerationProgress from './GenerationProgress'

interface Props {
  shared: MeetingSharedNotes | null
  progress?: MeetingProgress | null
  generating?: boolean
  disabled?: boolean
  showCommon?: boolean
  onChange?: (commonBody: string, unassignedBody: string) => void
}

export default function MeetingSharedPanel({
  shared,
  progress,
  generating = false,
  disabled = false,
  showCommon = false,
  onChange,
}: Props) {
  const id = useId()
  const commonBody = shared?.common_report?.body ?? ''
  const unassignedBody = shared?.unassigned_report?.body ?? ''
  const previews = progress?.previews.filter((preview) => preview.section !== 'deal') ?? []
  if (
    !showCommon &&
    !shared?.common_report &&
    !shared?.unassigned_report &&
    !previews.length &&
    !generating
  )
    return null

  return (
    <section className={styles.panel} aria-label="미팅 공통·미지정 기록" aria-busy={generating}>
      <div className={styles.heading}>
        <h2>미팅 공통 기록</h2>
        <span>공통 내용 아래에 딜 미지정 내용을 함께 표시</span>
      </div>
      {generating && previews.length === 0 && (
        <div className={styles.section}>
          <GenerationProgress progress={progress} fieldCount={1} />
        </div>
      )}
      {previews.map((preview) => (
        <div className={styles.section} key={preview.section}>
          <p className={styles.note}>
            {preview.section === 'common' ? '공통 내용' : '딜 미지정 · 확인 필요'}
          </p>
          <GenerationProgress progress={progress} preview={preview} fieldCount={1} />
        </div>
      ))}

      {!generating &&
        [
          {
            key: 'common',
            title: '공통 내용',
            report: shared?.common_report,
            value: commonBody,
            change: (value: string) => onChange?.(value, unassignedBody),
          },
          {
            key: 'unassigned',
            title: '딜 미지정 · 확인 필요',
            report: shared?.unassigned_report,
            value: unassignedBody,
            change: (value: string) => onChange?.(commonBody, value),
          },
        ]
          .filter((part) => part.report || (showCommon && part.key === 'common'))
          .map((part) => (
            <div className={styles.section} key={part.key}>
              {onChange ? (
                <>
                  <label htmlFor={id + part.key}>{part.title}</label>
                  <textarea
                    id={id + part.key}
                    rows={4}
                    value={part.value}
                    disabled={disabled}
                    placeholder="기록된 내용이 없습니다."
                    onChange={(event) => part.change(event.target.value)}
                  />
                  <p className={styles.printText}>{part.value || '기록된 내용 없음'}</p>
                </>
              ) : (
                <>
                  <h3>{part.title}</h3>
                  <p className={styles.text}>{part.value}</p>
                </>
              )}
            </div>
          ))}
    </section>
  )
}
