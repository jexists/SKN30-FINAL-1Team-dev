// 오른쪽 작업 영역. 왼쪽 탭이 무엇이든 이 자리는 늘 최종 보고서입니다.
//
// 화면에서 유일하게 떠 있는 흰 면입니다. 그것만으로 "지금 고치는 것은 여기" 가
// 전달되므로 안내 문구를 덧붙이지 않습니다.
import Button from '@/components/Button'
import type { ReportTemplate } from '@/types'

import type { MeetingPhase } from '../../useMeetingDraft'
import GenerationProgress from '../GenerationProgress'
import ReportDocument from '../ReportDocument'

import styles from './ReportSheet.module.scss'

interface Props {
  phase: MeetingPhase
  template: ReportTemplate
  title: string
  onTitleChange: (value: string) => void
  /** 미팅한 날. 제목 아래에 한 줄로 놓습니다. */
  when: string
  values: Record<string, string>
  /** 편집기를 다시 세워야 할 때 올라갑니다. */
  docKey: number
  onChange: (values: Record<string, string>, missingSections: string[]) => void
  /** 문서에서 사라진 항목 제목. 있으면 저장을 막습니다. */
  sectionIssues: string[]
  onRestoreSections: () => void
  evidence?: string
  /** 지금 몇 번째 단계인지. phase 가 generating 일 때만 씁니다. */
  generationStep: number
  /** 만들지 못한 이유. 눌러 본 자리 옆에서 보여야 무엇이 실패한 것인지 압니다. */
  generationError: string | null
  onRetryGenerate: () => void
  locked: boolean
  saving: boolean
  hasAiOriginal: boolean
  onStartManual: () => void
  onRegenerate: () => void
  onSave: () => void
}

export default function ReportSheet({
  phase,
  template,
  title,
  onTitleChange,
  when,
  values,
  docKey,
  onChange,
  sectionIssues,
  onRestoreSections,
  evidence,
  generationStep,
  generationError,
  onRetryGenerate,
  locked,
  saving,
  hasAiOriginal,
  onStartManual,
  onRegenerate,
  onSave,
}: Props) {
  const empty = phase === 'idle'
  const broken = sectionIssues.length > 0

  return (
    <div className={styles.root}>
      <article className={styles.sheet}>
        {/*
          실패는 눌러 본 자리 옆이 아니라 결과가 나왔어야 할 자리에서 알립니다.
          참고 열 구석의 작은 글씨는 기다리다 지친 사람의 눈에 들어오지 않습니다.
        */}
        {generationError && phase !== 'generating' && (
          <div className={styles.failed} role="alert">
            <p>{generationError}</p>
            <Button
              variant="outline"
              size="sm"
              type="button"
              disabled={locked || saving}
              onClick={onRetryGenerate}
            >
              다시 시도
            </Button>
          </div>
        )}

        {empty ? (
          <div className={styles.blank}>
            <h2>아직 보고서가 작성되지 않았습니다</h2>
            <p>위에 미팅 내용을 입력한 뒤 ‘AI 보고서 작성’을 누르세요. 직접 써도 됩니다.</p>
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
                placeholder="보고서 제목을 적으세요"
                onChange={(event) => onTitleChange(event.target.value)}
              />
              <p className={styles.when}>{when}</p>
            </div>

            {phase === 'generating' ? (
              <GenerationProgress step={generationStep} fieldCount={template.fields.length} />
            ) : (
              <>
                <ReportDocument
                  template={template}
                  values={values}
                  docKey={docKey}
                  disabled={locked}
                  onChange={onChange}
                />
                {evidence && <p className={styles.evidence}>{evidence}</p>}
              </>
            )}
          </>
        )}
      </article>

      <div className={styles.actions}>
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

        <Button
          type="button"
          className={styles.submit}
          disabled={locked || saving || empty || broken}
          onClick={onSave}
        >
          저장
        </Button>
      </div>

      {/*
        항목 제목이 사라지면 그 아래 글이 어느 항목인지 알 수 없습니다. 짐작해서
        저장하면 조용히 엉뚱한 자리에 들어가므로, 여기서 멈추고 되돌릴 길을 줍니다.
      */}
      {broken && (
        <div className={styles.broken} role="alert">
          <p>
            {sectionIssues.join(', ')} 제목이 문서에서 사라졌습니다. 되살린 뒤 저장할 수 있습니다.
          </p>
          <Button variant="outline" size="sm" type="button" onClick={onRestoreSections}>
            제목 되살리기
          </Button>
        </div>
      )}
    </div>
  )
}
