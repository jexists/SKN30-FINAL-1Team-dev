// AI 가 보고서를 쓰는 동안 보고서 자리를 지키는 화면.
//
// 자리표시자만 두면 "멈춘 것인지 도는 것인지" 를 알 수 없습니다. 그래서 도는 것
// 하나(아이콘)와 지금 무엇을 하는지 한 줄, 그리고 결과가 들어올 자리(자리표시자)를
// 함께 둡니다.
//
// 퍼센트는 두지 않습니다. 서버가 진행률을 주지 않으므로 숫자를 만들면 거짓말이 됩니다.
import { CheckIcon, RefreshIcon } from '@/components/icons'
import Skeleton from '@/components/Skeleton'

import { GENERATION_STEPS } from '../../useGenerationSteps'

import styles from './GenerationProgress.module.scss'

interface Props {
  /** 지금 몇 번째 단계인지. GENERATION_STEPS 의 자리입니다. */
  step: number
  /** 채워질 항목 수. 자리표시자를 실제 보고서 길이에 맞춥니다. */
  fieldCount: number
}

export default function GenerationProgress({ step, fieldCount }: Props) {
  return (
    <div className={styles.root}>
      <div className={styles.head} role="status" aria-live="polite">
        <RefreshIcon className={styles.spin} width={16} height={16} aria-hidden="true" />
        <p className={styles.headline}>{GENERATION_STEPS[step]}</p>
      </div>

      <ol className={styles.steps}>
        {GENERATION_STEPS.map((label, at) => {
          const state = at < step ? 'done' : at === step ? 'now' : 'todo'
          return (
            <li key={label} className={styles[state]}>
              <span className={styles.mark} aria-hidden="true">
                {state === 'done' ? <CheckIcon width={13} height={13} /> : <i />}
              </span>
              {label}
            </li>
          )
        })}
      </ol>

      {/*
        결과가 들어올 자리. 낭독은 위 한 줄이 이미 맡으므로 SkeletonBlocks 를 쓰지 않고
        조각만 놓습니다. 살아 있는 영역이 둘이면 단계가 바뀔 때마다 두 번 읽힙니다.
      */}
      <div className={styles.blocks}>
        {Array.from({ length: fieldCount }, (_, at) => (
          <Skeleton key={at} height={76} radius="var(--r-sm)" />
        ))}
      </div>
    </div>
  )
}
