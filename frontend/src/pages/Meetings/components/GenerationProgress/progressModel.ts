import type { MeetingProgress, MeetingStageResult } from '@/types'

/**
 * 활동 한 줄의 상태.
 *
 *   live    지금 서버가 하고 있는 일. 화면에 언제나 하나뿐입니다.
 *   done    끝난 일. 회색으로 내려앉아 멈춥니다.
 *   running 보고서와 나란히 도는 곁일(ML 분석). 끝나지 않았으므로 done 이 아니고,
 *           단계 진행도 아니므로 live 를 뺏지 않습니다.
 */
export type ActivityState = 'done' | 'live' | 'running'

export interface ActivityRow {
  key: string
  label: string
  state: ActivityState
  detail?: string
}

/** 단계 이름 → 진행 중/끝났을 때의 활동 문구. */
const STEP_LABELS: Record<string, { live: string; done: string }> = {
  분석: { live: '미팅 내용 분석 중', done: '미팅 내용 분석함' },
  '자료 정리': { live: '자료 정리 중', done: '자료 정리함' },
  작성: { live: '보고서 작성 중', done: '보고서 작성함' },
  검토: { live: '근거·표현 검토 중', done: '근거·표현 검토함' },
  '필요 시 수정': { live: '초안 수정 중', done: '초안 수정함' },
  '사용자 확인': { live: '보고서 마무리 중', done: '보고서 마무리함' },
}

// 미팅은 딜마다 한 편씩 씁니다. 같은 '작성' 단계라도 하는 일이 다릅니다.
const MEETING_WRITING = { live: '딜별 보고서 작성 중', done: '딜별 보고서 작성함' }

/*
 * 오래 걸리는 단계에서 돌려 보여 줄 문구.
 *
 * 규칙 하나만 지킵니다: 그 단계가 실제로 하는 일 안에서만 씁니다. 화면이 서버가 하지 않는
 * 일을 말하면, 근거를 다루는 이 도구에서 가장 먼저 잃는 것이 신뢰입니다.
 *
 *   content_analysis  원문을 문장 단위로 쪼개고(build_evidence_ledger) 딜에 귀속시킨 뒤
 *                     (SegmentAssignment) 불명확한 것을 다시 붙입니다
 *                     (backend/app/agents/meeting/content.py, refinement.py)
 *   report_writing    배정된 scope 의 근거·CRM·과거 보고서를 읽고 본문을 씁니다
 *                     (skills/sales-meeting-report/SKILL.md)
 *   report_review     근거와 본문을 맞춰 보고 단정·추측을 걸러냅니다
 */
const STAGE_PHRASES: Record<string, string[]> = {
  content_analysis: [
    '미팅 원문을 문장 단위로 나누는 중',
    '내용을 딜별로 나눠 붙이는 중',
    '귀속이 불명확한 내용을 다시 확인하는 중',
  ],
  report_preparing: ['모아 둔 자료를 읽는 중', '보고서에 쓸 근거를 고르는 중'],
  report_writing: ['배정된 근거를 읽는 중', '본문을 쓰는 중', '담당·기한·완료 기준을 확인하는 중'],
  report_review: ['근거와 본문을 맞춰 보는 중', '단정한 표현이 없는지 살피는 중'],
  report_revising: ['지적된 문장을 고치는 중'],
}

/** 지금 단계에서 돌려 보여 줄 문구. 없으면 빈 배열입니다. */
export function stagePhrases(progress: MeetingProgress | null | undefined): string[] {
  return STAGE_PHRASES[progress?.stage ?? ''] ?? STAGE_PHRASES.content_analysis
}

function stepsOf(progress: MeetingProgress | null | undefined, reportKind: 'meeting' | 'period') {
  const period =
    reportKind === 'period' || ['daily', 'weekly', 'monthly'].includes(progress?.report_kind ?? '')
  const steps = period
    ? ['자료 정리', '작성', '검토', '필요 시 수정', '사용자 확인']
    : ['분석', '작성', '검토', '필요 시 수정', '사용자 확인']
  const stepByStage: Record<string, string> = period
    ? {
        report_preparing: '자료 정리',
        report_writing: '작성',
        report_review: '검토',
        report_revising: '필요 시 수정',
        report_complete: '사용자 확인',
      }
    : {
        content_analysis: '분석',
        report_writing: '작성',
        report_review: '검토',
        report_revising: '필요 시 수정',
        report_complete: '사용자 확인',
      }
  // 아직 아무 단계도 오지 않았으면(queued·starting) 첫 단계가 이미 돌고 있는 것입니다.
  // 따로 "준비하는 중입니다" 를 지어내지 않습니다.
  return { period, steps, currentStep: stepByStage[progress?.stage ?? ''] ?? steps[0] }
}

function labelsOf(step: string, period: boolean) {
  return !period && step === '작성' ? MEETING_WRITING : STEP_LABELS[step]
}

export function progressModel(
  progress: MeetingProgress | null | undefined,
  reportKind: 'meeting' | 'period',
): {
  label: string
  steps: string[]
  currentStep: string
  countLabel?: string
  recoveryLabel?: string
} {
  const { period, steps, currentStep } = stepsOf(progress, reportKind)
  const counts = progress?.phase_counts
  const unit =
    counts &&
    (counts.phase === 'prepare'
      ? '자료'
      : ['synthesize', 'write_initial', 'repair'].includes(counts.phase)
        ? '본문'
        : counts.phase === 'review_initial'
          ? '검토'
          : '항목')
  const countLabel =
    counts && counts.total > 0
      ? `${unit} ${counts.total}개 중 ${counts.completed}개 완료${counts.failed ? ` · 실패 ${counts.failed}` : ''}`
      : undefined
  const recoveryLabel =
    progress?.recovery_reason === 'original_source_fallback'
      ? '일부 자료 요약에 실패해 원문으로 계속 작성합니다.'
      : progress?.recovery_reason === 'valid_draft_fallback'
        ? '검토·수정 중 문제가 있어 이전 초안을 유지합니다.'
        : undefined
  return {
    label: labelsOf(currentStep, period).live,
    steps,
    currentStep,
    countLabel,
    recoveryLabel,
  }
}

function countOf(results: MeetingStageResult[] | undefined, stage: string): number {
  return results?.filter((item) => item.stage === stage).length ?? 0
}

/** 살아 있는 줄에만 붙는 부연. 끝난 줄은 숫자를 달고 있을 이유가 없습니다. */
function liveDetail(progress: MeetingProgress | null | undefined, countLabel?: string) {
  const parts = [countLabel]
  if (progress?.stage === 'report_review' && progress.review_attempt != null) {
    parts.push(
      `검토 ${progress.review_attempt}${progress.review_limit ? `/${progress.review_limit}` : ''}회`,
    )
  }
  const detail = parts.filter(Boolean).join(' · ')
  return detail || undefined
}

/**
 * 서버 진행 상태를 활동 로그 줄로 폅니다.
 *
 * 지나온 단계는 done 으로 쌓이고, 지금 단계 하나만 live 입니다. 아직 오지 않은
 * 단계는 내보내지 않습니다 — 하지도 않은 일을 미리 늘어놓지 않습니다.
 *
 * @param extras 보고서와 나란히 도는 곁일. 단계 뒤에 붙습니다.
 */
export function activityRows(
  progress: MeetingProgress | null | undefined,
  reportKind: 'meeting' | 'period',
  extras: ActivityRow[] = [],
): ActivityRow[] {
  const { period, steps, currentStep } = stepsOf(progress, reportKind)
  const { countLabel } = progressModel(progress, reportKind)
  const index = steps.indexOf(currentStep)
  const results = progress?.stage_results
  const classified = countOf(results, 'content_analysis')
  const prepared = countOf(results, 'prepare')
  const rows: ActivityRow[] = []

  steps.slice(0, index + 1).forEach((step, position) => {
    const done = position < index
    const labels = labelsOf(step, period)
    // 자료 정리는 미팅에 따로 단계가 없습니다. 쓰기 직전에 끝난 일로 한 줄 세웁니다.
    if (!period && step === '작성' && prepared) {
      rows.push({ key: 'prepare', label: `자료 ${prepared}건 정리함`, state: 'done' })
    }
    // 분석이 한 일은 개수로 말합니다. 끝난 줄은 "무엇을 몇 건" 이 곧 결과입니다.
    const analysed = !period && step === '분석' && classified
    rows.push({
      key: step,
      label: done ? (analysed ? `근거 ${classified}건 분류함` : labels.done) : labels.live,
      state: done ? 'done' : 'live',
      detail: done
        ? undefined
        : analysed
          ? `근거 ${classified}건 분류함`
          : liveDetail(progress, countLabel),
    })
  })

  return [...rows, ...extras]
}
