// 오른쪽 작업 영역. 왼쪽 탭이 무엇이든 이 자리는 늘 최종 보고서입니다.
//
// 화면에서 유일하게 떠 있는 흰 면입니다. 그것만으로 "지금 고치는 것은 여기" 가
// 전달되므로 안내 문구를 덧붙이지 않습니다.
import { useId } from 'react'

import Button from '@/components/Button'
import Skeleton from '@/components/Skeleton'
import type { MeetingPreview, MeetingProgress } from '@/types'

import type { MeetingPhase } from '../../useMeetingDraft'
import GenerationProgress from '../GenerationProgress'
import ReportDocument from '../ReportDocument'

import styles from './ReportSheet.module.scss'

interface Props {
  phase: MeetingPhase
  titleId?: string
  title: string
  onTitleChange: (value: string) => void
  /** 미팅한 날. 제목 아래에 한 줄로 놓습니다. */
  when: string
  body: string
  /** 편집기를 다시 세워야 할 때 올라갑니다. */
  docKey: number
  onChange: (body: string) => void
  evidence?: string
  /** 서버가 보낸 실행 상태와 검토 전 초안. 최종 편집기 값으로 쓰지 않습니다. */
  generationProgress?: MeetingProgress | null
  generationPreview?: MeetingPreview
  /** 만들지 못한 이유. 눌러 본 자리 옆에서 보여야 무엇이 실패한 것인지 압니다. */
  generationError: string | null
  onRetryGenerate: () => void
  /** 서버가 Agent 실행을 허용하지 않는 상태입니다. 편집·저장은 계속 가능합니다. */
  generationDisabled?: boolean
  locked: boolean
  saving: boolean
  onStartManual: () => void
  onRegenerate: () => void
  regenerateLabel?: string
  /** 딜 카드가 바깥 면을 맡을 때 시트의 중복 테두리·sticky를 걷습니다. */
  embedded?: boolean
}

export default function ReportSheet({
  phase,
  titleId,
  title,
  onTitleChange,
  when,
  body,
  docKey,
  onChange,
  evidence,
  generationProgress,
  generationPreview,
  generationError,
  onRetryGenerate,
  generationDisabled = false,
  locked,
  saving,
  onStartManual,
  onRegenerate,
  regenerateLabel = 'AI 다시 생성',
  embedded = false,
}: Props) {
  const generatedTitleId = useId()
  const inputId = titleId ?? generatedTitleId
  const empty = phase === 'idle'

  return (
    <div className={`${styles.root} ${embedded ? styles.embedded : ''}`}>
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
              disabled={locked || saving || generationDisabled}
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
              {phase === 'generating' ? (
                <Skeleton width="68%" height={39} radius="var(--r-sm)" />
              ) : (
                <>
                  <label className="sr-only" htmlFor={inputId}>
                    보고서 제목
                  </label>
                  <input
                    id={inputId}
                    className={styles.title}
                    value={title}
                    disabled={locked}
                    placeholder="보고서 제목을 적으세요"
                    onChange={(event) => onTitleChange(event.target.value)}
                  />
                </>
              )}
              <p className={styles.when}>{when}</p>
            </div>

            {phase === 'generating' ? (
              <GenerationProgress
                progress={generationProgress}
                preview={generationPreview}
                fieldCount={1}
              />
            ) : (
              <>
                <ReportDocument body={body} docKey={docKey} disabled={locked} onChange={onChange} />
                {evidence && <p className={styles.evidence}>{evidence}</p>}
              </>
            )}
          </>
        )}
      </article>

      {!empty && (
        <div className={styles.actions}>
          <Button
            variant="outline"
            type="button"
            disabled={locked || saving || generationDisabled || phase === 'generating'}
            onClick={onRegenerate}
          >
            {regenerateLabel}
          </Button>
        </div>
      )}
    </div>
  )
}
