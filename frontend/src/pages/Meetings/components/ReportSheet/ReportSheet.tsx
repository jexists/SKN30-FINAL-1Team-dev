// 오른쪽 작업 영역. 왼쪽 탭이 무엇이든 이 자리는 늘 최종 보고서입니다.
//
// 화면에서 유일하게 떠 있는 흰 면입니다. 그것만으로 "지금 고치는 것은 여기" 가
// 전달되므로 안내 문구를 덧붙이지 않습니다.
import Button from '@/components/Button'
import ReportFields from '@/components/ReportFields'
import { SkeletonBlocks } from '@/components/Skeleton'
import type { ReportTemplate } from '@/types'

import type { MeetingPhase } from '../../useMeetingDraft'

import styles from './ReportSheet.module.scss'

interface Props {
  phase: MeetingPhase
  template: ReportTemplate
  title: string
  onTitleChange: (value: string) => void
  /** 미팅한 날. 제목 아래에 한 줄로 놓습니다. */
  when: string
  values: Record<string, string>
  aiFilledIds: ReadonlySet<string>
  onChange: (id: string, value: string) => void
  evidence?: string
  /** 확정을 막는 항목들. 비어 있으면 저장할 수 있습니다. */
  missing: string[]
  locked: boolean
  saving: boolean
  hasAiOriginal: boolean
  onStartManual: () => void
  onSaveDraft: () => void
  onRegenerate: () => void
  onPrint: () => void
  onSubmit: () => void
}

export default function ReportSheet({
  phase,
  template,
  title,
  onTitleChange,
  when,
  values,
  aiFilledIds,
  onChange,
  evidence,
  missing,
  locked,
  saving,
  hasAiOriginal,
  onStartManual,
  onSaveDraft,
  onRegenerate,
  onPrint,
  onSubmit,
}: Props) {
  const empty = phase === 'idle'

  return (
    <div className={styles.root}>
      <article className={styles.sheet}>
        {empty ? (
          <div className={styles.blank}>
            <h2>아직 보고서가 없습니다</h2>
            <p>왼쪽에 미팅 내용을 입력한 뒤 ‘AI 보고서 작성’을 누르세요. 직접 써도 됩니다.</p>
            <Button variant="outline" type="button" disabled={locked} onClick={onStartManual}>
              직접 작성하기
            </Button>
          </div>
        ) : (
          <>
            <div className={styles.titleBlock}>
              <label className="sr-only" htmlFor="report-title">
                보고서 제목
              </label>
              <input
                id="report-title"
                className={styles.title}
                value={title}
                disabled={locked}
                placeholder="보고서 제목"
                onChange={(event) => onTitleChange(event.target.value)}
              />
              <p className={styles.when}>{when}</p>
            </div>

            {phase === 'generating' ? (
              <SkeletonBlocks
                label="AI가 보고서를 작성하는 중입니다."
                count={template.fields.length}
                height={76}
                radius="var(--r-sm)"
                gap={20}
              />
            ) : (
              <>
                <ReportFields
                  template={template}
                  values={values}
                  readOnly={locked}
                  aiFilledIds={aiFilledIds}
                  onChange={onChange}
                />
                {evidence && <p className={styles.evidence}>{evidence}</p>}
              </>
            )}
          </>
        )}
      </article>

      <div className={styles.actions}>
        <Button variant="outline" type="button" disabled={locked || saving} onClick={onSaveDraft}>
          {saving ? '저장 중…' : '임시저장'}
        </Button>

        {hasAiOriginal && (
          <Button
            variant="outline"
            type="button"
            disabled={locked || saving || phase === 'generating'}
            onClick={onRegenerate}
          >
            AI 다시 생성
          </Button>
        )}

        <Button variant="outline" type="button" disabled={empty} onClick={onPrint}>
          PDF 다운로드
        </Button>

        <Button
          type="button"
          className={styles.submit}
          disabled={locked || saving || empty || missing.length > 0}
          onClick={onSubmit}
        >
          확정하고 저장
        </Button>
      </div>

      {!empty && missing.length > 0 && (
        <p className={styles.missing}>확정 전 확인: {missing.join(', ')}</p>
      )}
    </div>
  )
}
