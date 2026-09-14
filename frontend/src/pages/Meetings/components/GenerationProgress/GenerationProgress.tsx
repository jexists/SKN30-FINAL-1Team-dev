// 서버가 지금 하고 있는 일 한 줄과, 흘러나오는 본문.
//
// 지나온 단계는 회색으로 쌓이고 살아 있는 줄은 언제나 하나뿐입니다. 여기 있는 글은
// 아직 검토되지 않았으므로 저장·편집기 값으로 쓰지 않습니다 — 읽기 전용입니다.
import ReportView from '@/components/ReportView'
import type { MeetingPreview, MeetingProgress } from '@/types'

import ActivityList from './ActivityList'
import styles from './GenerationProgress.module.scss'
import { activityRows, progressModel, stagePhrases, type ActivityRow } from './progressModel'
import useLiveDetail from './useLiveDetail'
import useStreamedText from './useStreamedText'

interface Props {
  progress?: MeetingProgress | null
  preview?: MeetingPreview
  previews?: MeetingPreview[]
  /** 보고서와 나란히 도는 곁일. 단계 줄 뒤에 붙습니다. */
  extras?: ActivityRow[]
  /**
   * 진행 줄을 여기서 어떻게 낼지. 한 화면에서 'steps' 와 'live' 를 한 번씩 씁니다 —
   * 같은 문구가 상자마다 뜨면 화면에 서너 개씩 보이므로 상자 안에서는 끕니다.
   *
   *   'steps'  지나온 단계와 곁일. 흐름 맨 위에.
   *   'live'   지금 하는 일 한 줄. 흐름 맨 아래에 — 바닥까지 내려 읽어도 보입니다.
   *   false    내지 않음.
   */
  feed?: false | 'steps' | 'live'
  /** 지금 서버가 손대고 있는 자리. live 줄에만 붙습니다. */
  liveTarget?: string
  reportKind?: 'meeting' | 'period'
}

/** 최종 본문이 설 자리에서, 최종 본문과 같은 컴포넌트로 흐릅니다. */
function StreamedBody({ body }: { body: string }) {
  const shown = useStreamedText(body)
  return <ReportView className={styles.stream} body={shown} />
}

export default function GenerationProgress({
  progress,
  preview,
  previews,
  extras,
  feed = 'steps',
  liveTarget,
  reportKind = 'meeting',
}: Props) {
  const model = progressModel(progress, reportKind)
  // 오래 걸리는 단계에서도 화면이 멈춰 있지 않게 합니다. 초는 실제로 흐른 시간이고,
  // 문구는 그 단계가 실제로 하는 일입니다.
  const live = useLiveDetail(model.currentStep, stagePhrases(progress))
  const visiblePreviews = [
    ...(previews ?? []),
    ...(preview &&
    !(previews ?? []).some(
      (item) => item.revision === preview.revision && item.section === preview.section,
    )
      ? [preview]
      : []),
  ]
  const rows = activityRows(progress, reportKind, extras)
  /*
   * 살아 있는 줄은 흐름 맨 아래에 혼자 섭니다. 검토·수정 단계에서는 본문이 위에서 제자리로
   * 바뀌므로, 아래에서 읽는 사람에게는 이 한 줄이 유일한 "아직 돌고 있다" 입니다.
   */
  const liveRow = rows.find((row) => row.state === 'live')
  const liveRows = liveRow
    ? [
        {
          ...liveRow,
          label: live.phrase ?? liveRow.label,
          // 갓 시작한 줄에 '0초' 를 달지 않습니다. 기다림이 느껴질 때부터 셉니다.
          detail: [liveRow.detail, liveTarget, live.seconds >= 3 ? `${live.seconds}초` : null]
            .filter(Boolean)
            .join(' · '),
        },
      ]
    : []

  return (
    <div className={styles.root}>
      {feed === 'steps' && (
        <>
          {/* 화면은 줄 목록으로 말합니다. 읽어 주는 쪽에는 바뀌지 않는 한 문장이면 됩니다. */}
          <p className="sr-only" role="status" aria-live="polite">
            {model.label}
          </p>
          <ActivityList
            rows={rows.filter((row) => row.state !== 'live')}
            label="보고서 진행 단계"
          />
        </>
      )}

      {visiblePreviews.map((item) => (
        <StreamedBody key={`${item.section}:${item.sales_deal_id ?? ''}`} body={item.body} />
      ))}

      {feed === 'live' && <ActivityList rows={liveRows} label="지금 하는 일" />}

      {feed === 'steps' && model.recoveryLabel && (
        <p className={styles.recovery}>{model.recoveryLabel}</p>
      )}
    </div>
  )
}
