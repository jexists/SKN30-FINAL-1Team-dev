import { useEffect, useId, useState } from 'react'

import Button from '@/components/Button'
import type {
  MeetingAssignmentOverride,
  MeetingDealRef,
  MeetingEvidenceLedger,
  MeetingProgress,
  MeetingSharedNotes,
} from '@/types'

import styles from './MeetingSharedPanel.module.scss'
import GenerationProgress from './GenerationProgress'

interface Props {
  shared: MeetingSharedNotes | null
  progress?: MeetingProgress | null
  evidence?: MeetingEvidenceLedger
  deals?: MeetingDealRef[]
  disabled?: boolean
  canReassign?: boolean
  onDirtyChange?: (dirty: boolean) => void
  onSave?: (common: string | null, unassigned: string | null) => void
  onAssign?: (assignments: MeetingAssignmentOverride[]) => void
}

export default function MeetingSharedPanel({
  shared,
  progress,
  evidence,
  deals = [],
  disabled = false,
  canReassign = false,
  onDirtyChange,
  onSave,
  onAssign,
}: Props) {
  const id = useId()
  const common = shared?.common_report?.body ?? ''
  const unassigned = shared?.unassigned_report?.body ?? ''
  const [commonBody, setCommonBody] = useState(common)
  const [unassignedBody, setUnassignedBody] = useState(unassigned)
  const [assignments, setAssignments] = useState<Record<string, string[]>>({})

  useEffect(() => {
    setCommonBody(common)
    setUnassignedBody(unassigned)
  }, [common, unassigned, shared?.run_id, shared?.revision])
  useEffect(() => {
    setAssignments({})
  }, [shared?.run_id, evidence?.transcript_sha256])

  const unresolved =
    evidence?.items.filter(
      (item) =>
        item.applicability.scope === 'unresolved' || item.applicability.scope === 'out_of_scope',
    ) ?? []
  const dirty = commonBody !== common || unassignedBody !== unassigned
  useEffect(() => {
    onDirtyChange?.(dirty)
  }, [dirty, onDirtyChange])
  const hasNotes = !!(shared?.common_report || shared?.unassigned_report)
  const hasEmptyNote =
    (!!shared?.common_report && !commonBody.trim()) ||
    (!!shared?.unassigned_report && !unassignedBody.trim())
  const overrides: MeetingAssignmentOverride[] = Object.entries(assignments)
    .filter(([, ids]) => ids.length > 0)
    .map(([segment_id, deal_ids]) => ({ segment_id, applicability: { scope: 'deal', deal_ids } }))

  const previews = progress?.previews.filter((preview) => preview.section !== 'deal') ?? []
  if (!hasNotes && !(onAssign && unresolved.length) && !previews.length) return null

  return (
    <section className={styles.panel} aria-label="미팅 공통·미지정 기록">
      <div className={styles.heading}>
        <h2>미팅 공통 기록</h2>
        <span>공통 내용은 각 딜 보고서에 함께 포함</span>
      </div>
      {onSave && (
        <p className={styles.note}>아래 메모를 고쳐도 원문과 근거 배정은 바뀌지 않습니다.</p>
      )}
      {previews.map((preview) => (
        <div className={styles.section} key={preview.section}>
          <p className={styles.note}>
            {preview.section === 'common' ? '공통 내용' : '딜 미지정 · 확인 필요'}
          </p>
          <GenerationProgress progress={progress} preview={preview} fieldCount={1} />
        </div>
      ))}

      {[
        {
          key: 'common',
          title: '공통 내용',
          report: shared?.common_report,
          value: commonBody,
          change: setCommonBody,
        },
        {
          key: 'unassigned',
          title: '딜 미지정 · 확인 필요',
          report: shared?.unassigned_report,
          value: unassignedBody,
          change: setUnassignedBody,
        },
      ]
        .filter((part) => part.report)
        .map((part) => (
          <div className={styles.section} key={part.key}>
            <label htmlFor={onSave ? id + part.key : undefined}>{part.title}</label>
            {onSave ? (
              <>
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
              <p className={styles.text}>{part.value}</p>
            )}
            {onSave && part.report?.ai_body && part.report.ai_body !== part.report.body && (
              <details className={styles.proposal}>
                <summary>새 AI 제안 확인</summary>
                <p className={styles.note}>
                  직접 수정한 기록은 유지됩니다. 제안을 적용한 뒤 메모를 저장할 수 있습니다.
                </p>
                <p className={styles.text}>{part.report.ai_body}</p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={disabled || part.value === part.report.ai_body}
                  onClick={() => part.change(part.report!.ai_body!)}
                >
                  이 제안으로 바꾸기
                </Button>
              </details>
            )}
          </div>
        ))}

      {onSave && hasNotes && (
        <div className={styles.actions}>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={disabled || !dirty || hasEmptyNote}
            onClick={() =>
              onSave(
                commonBody.trim() ? commonBody : null,
                unassignedBody.trim() ? unassignedBody : null,
              )
            }
          >
            공통·미지정 메모 저장
          </Button>
          {dirty && <span className={styles.note}>저장하지 않은 변경사항</span>}
          {hasEmptyNote && (
            <span className={styles.warning}>기록을 빈 내용으로 저장할 수 없습니다.</span>
          )}
        </div>
      )}

      {onAssign && unresolved.length > 0 && (
        <details className={styles.assignments}>
          <summary>
            미지정 원문 확인·딜 배정 <span>{unresolved.length}개 구간</span>
          </summary>
          <p className={styles.note}>
            해당하는 딜을 복수 선택할 수 있습니다. 선택하지 않은 구간은 미지정 상태로 유지됩니다.
          </p>
          {!canReassign && (
            <p className={styles.warning}>
              원문·선택 딜이 바뀌었거나 다시 생성할 수 없는 보고서가 있습니다. 원문 또는 딜을
              바꿨다면 미팅 전체를 새로 생성한 뒤 배정하세요.
            </p>
          )}
          {unresolved.map(({ segment, applicability }) => (
            <fieldset key={segment.segment_id} disabled={disabled || !canReassign || dirty}>
              <legend>
                {segment.segment_id} ·{' '}
                {applicability.scope === 'out_of_scope' ? '선택 딜 밖의 내용' : '딜 확인 필요'}
              </legend>
              <p className={styles.quote}>{segment.text}</p>
              <div className={styles.choices}>
                {deals.map((deal) => (
                  <label key={deal.id}>
                    <input
                      type="checkbox"
                      checked={(assignments[segment.segment_id] ?? []).includes(deal.id)}
                      onChange={() =>
                        setAssignments((previous) => {
                          const selected = previous[segment.segment_id] ?? []
                          return {
                            ...previous,
                            [segment.segment_id]: selected.includes(deal.id)
                              ? selected.filter((one) => one !== deal.id)
                              : [...selected, deal.id],
                          }
                        })
                      }
                    />
                    <span>
                      {deal.label}
                      {deal.note && <small>{deal.note}</small>}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
          {dirty && <p className={styles.warning}>수정한 메모를 먼저 저장한 후 딜을 배정하세요.</p>}
          <Button
            type="button"
            size="sm"
            disabled={disabled || !canReassign || dirty || overrides.length === 0}
            onClick={() => onAssign(overrides)}
          >
            선택한 딜로 배정하고 미팅 전체 다시 생성
          </Button>
        </details>
      )}
    </section>
  )
}
