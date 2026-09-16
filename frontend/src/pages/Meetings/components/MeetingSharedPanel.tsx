import ReportView from '@/components/ReportView'
import type { MeetingProgress, MeetingSharedNotes } from '@/types'

import EditableReport from './EditableReport'
import GenerationProgress from './GenerationProgress'
import styles from './MeetingSharedPanel.module.scss'

interface Props {
  shared: MeetingSharedNotes | null
  progress?: MeetingProgress | null
  generating?: boolean
  disabled?: boolean
  /** 화면 아래 [수정] 이 켜져 있는가. 잠긴 글은 켜져 있어도 읽기로 남습니다. */
  editing?: boolean
  showCommon?: boolean
  /** 공통·미지정 편집기를 각각 다시 세우는 값. 서로 커서를 밀지 않게 따로 셉니다. */
  commonDocKey?: number
  unassignedDocKey?: number
  onChange?: (commonBody: string, unassignedBody: string) => void
}

export default function MeetingSharedPanel({
  shared,
  progress,
  generating = false,
  disabled = false,
  editing = false,
  showCommon = false,
  commonDocKey = 0,
  unassignedDocKey = 0,
  onChange,
}: Props) {
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
        {onChange && <span>미팅 공통 내용과 확인이 필요한 기록</span>}
      </div>
      {previews.map((preview) => (
        <div
          className={`${styles.section} ${preview.section === 'unassigned' ? styles.needsReview : ''}`}
          key={preview.section}
        >
          {/* 판 머리가 이미 '미팅 공통 기록' 입니다. 갈래가 다른 미지정 기록에만 이름을 답니다. */}
          {preview.section === 'unassigned' && <p className={styles.note}>딜 미지정 · 확인 필요</p>}
          <GenerationProgress feed={false} progress={progress} preview={preview} />
        </div>
      ))}

      {!generating &&
        [
          {
            key: 'common',
            title: '공통 내용',
            report: shared?.common_report,
            value: commonBody,
            docKey: commonDocKey,
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
            docKey: unassignedDocKey,
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
                  {/* 딜 본문과 같은 방식입니다 — 화면 아래 [수정] 이 이 글도 함께 엽니다.
                      이름은 읽는 화면과 같은 규칙으로, 미지정 기록에만 답니다. */}
                  {part.key === 'unassigned' && <p className={styles.note}>{part.title}</p>}
                  <EditableReport
                    body={part.value}
                    docKey={part.docKey}
                    disabled={disabled}
                    editing={editing}
                    onChange={part.change}
                  />
                </>
              ) : (
                <>
                  {/* 판 머리가 이미 '미팅 공통 기록' 입니다. 그 아래 같은 말을 또
                      붙이지 않고, 갈래가 다른 미지정 기록에만 이름을 답니다. */}
                  {part.key === 'unassigned' && <h3>{part.title}</h3>}
                  {part.value.trim() ? (
                    <ReportView body={part.value} />
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
