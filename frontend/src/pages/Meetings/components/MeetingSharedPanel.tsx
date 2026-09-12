import { useId } from 'react'

import ReportBody from '@/components/ReportBody'
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
  const supporting =
    onChange &&
    !showCommon &&
    (generating ? previews.length > 1 : shared?.common_report && shared?.unassigned_report)
  if (
    !showCommon &&
    !shared?.common_report &&
    !shared?.unassigned_report &&
    !previews.length &&
    !generating
  )
    return null

  return (
    <section
      className={`${styles.panel} ${supporting ? styles.supporting : ''}`}
      aria-label="미팅 공통·미지정 기록"
      aria-busy={generating}
    >
      <div className={styles.heading}>
        <h2>미팅 공통 기록</h2>
        {onChange && <span>미팅 공통 내용과 확인이 필요한 기록</span>}
      </div>
      {generating && previews.length === 0 && (
        <div className={styles.section}>
          <GenerationProgress progress={progress} fieldCount={1} />
        </div>
      )}
      {previews.map((preview) => (
        <div
          className={`${styles.section} ${preview.section === 'unassigned' ? styles.needsReview : ''}`}
          key={preview.section}
        >
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
            /*
             * 어느 딜에도 붙지 않은 기록입니다. 쓰는 동안에는 '어느 딜 얘기인지
             * 보세요' 라는 할 일이지만, 제출한 보고서를 읽을 때는 더 확인할 것이
             * 없습니다. 그래서 읽는 화면에서는 사실만 말하고 주황도 걷습니다.
             */
            key: 'unassigned',
            title: onChange ? '딜 미지정 · 확인 필요' : '딜 미지정 기록',
            report: shared?.unassigned_report,
            value: unassignedBody,
            change: (value: string) => onChange?.(commonBody, value),
          },
        ]
          .filter((part) => part.report || (showCommon && part.key === 'common'))
          .map((part) => (
            <div
              className={`${styles.section} ${
                onChange && part.key === 'unassigned' ? styles.needsReview : ''
              }`}
              key={part.key}
            >
              {onChange ? (
                <>
                  <label htmlFor={id + part.key}>{part.title}</label>
                  <textarea
                    id={id + part.key}
                    rows={showCommon && part.key === 'common' ? 6 : 3}
                    value={part.value}
                    disabled={disabled}
                    placeholder="기록된 내용이 없습니다."
                    onChange={(event) => part.change(event.target.value)}
                  />
                  {part.value.trim() ? (
                    <ReportBody className={styles.printText} body={part.value} />
                  ) : (
                    <p className={`${styles.printText} ${styles.empty}`}>기록된 내용 없음</p>
                  )}
                </>
              ) : (
                <>
                  {/* 판 머리가 이미 '미팅 공통 기록' 입니다. 그 아래 같은 말을 또
                      붙이지 않고, 갈래가 다른 미지정 기록에만 이름을 답니다. */}
                  {part.key === 'unassigned' && <h3>{part.title}</h3>}
                  {part.value.trim() ? (
                    <ReportBody className={styles.text} body={part.value} />
                  ) : (
                    <p className={styles.empty}>기록된 내용 없음</p>
                  )}
                </>
              )}
            </div>
          ))}
    </section>
  )
}
