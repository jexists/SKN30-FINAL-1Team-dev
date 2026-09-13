import type { MeetingPreview, MeetingProgress } from '@/types'

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
  const period =
    reportKind === 'period' || ['daily', 'weekly', 'monthly'].includes(progress?.report_kind ?? '')
  const stage = progress?.stage
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
  const currentStep = stepByStage[stage ?? ''] ?? steps[0]
  const labelByStage: Record<string, string> = period
    ? {
        report_preparing: '보고서를 정리하고 있습니다.',
        report_writing: '보고서를 작성하는 중입니다',
        report_review: '보고서 근거와 표현을 검토하는 중입니다',
        report_revising: '수정 중인 초안',
        report_complete: '보고서가 준비되었습니다. 내용을 확인해 주세요.',
      }
    : {
        content_analysis: '미팅 내용을 딜별로 나누고 있습니다.',
        report_writing: '딜별 보고서를 작성하는 중입니다',
        report_review: '보고서 근거와 표현을 검토하는 중입니다',
        report_revising: '수정 중인 초안',
        report_complete: '보고서가 준비되었습니다. 내용을 확인해 주세요.',
      }
  const label =
    labelByStage[stage ?? ''] ??
    (period ? '보고서 자료 정리를 준비하는 중입니다' : '미팅 처리를 준비하는 중입니다')
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
  return { label, steps, currentStep, countLabel, recoveryLabel }
}

export function previewLabel(preview: MeetingPreview): string {
  if (preview.preview_state === 'confirmed') return '확정된 본문'
  return preview.draft_version && preview.draft_version > 1 ? '수정 중인 초안' : '작성 중인 초안'
}
