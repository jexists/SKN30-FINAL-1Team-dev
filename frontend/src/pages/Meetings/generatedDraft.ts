import type { DealAssessment } from '@/types'

/** 저장된 서버 분석을 읽습니다. ML 실패를 새로고침 후 대기로 숨기지 않습니다. */
export function readMeetingAnalysis(value: Record<string, unknown>) {
  const assessment = value.deal_assessment as Partial<DealAssessment> | null | undefined
  return {
    assessment:
      (assessment?.label === 'high' || assessment?.label === 'watch') &&
      typeof assessment.high_probability === 'number' &&
      typeof assessment.model_version === 'string'
        ? {
            label: assessment.label,
            high_probability: assessment.high_probability,
            model_version: assessment.model_version,
          }
        : undefined,
    analysisError:
      typeof value.analysis_error === 'string' && value.analysis_error
        ? value.analysis_error
        : undefined,
    reportError:
      typeof value.report_error === 'string' && value.report_error ? value.report_error : undefined,
  }
}

export async function transcriptDigest(transcript: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(transcript))
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

/** 다시 생성된 AI 원본과 사람이 보고 있는 최종본이 다른지 비교합니다. */
export function hasPendingAi(current: Record<string, string>, generated: Record<string, string>) {
  return Object.entries(generated).some(([id, value]) => value !== (current[id] ?? ''))
}

/** 원문이나 선택 딜이 달라지면 과거 segment ID의 배정을 재사용하지 않습니다. */
export function canReassignEvidence(
  sourceHash: string,
  currentHash: string | null,
  sourceDealIds: readonly string[],
  selectedDealIds: readonly string[],
) {
  return (
    !!currentHash &&
    sourceHash === currentHash &&
    sourceDealIds.length === selectedDealIds.length &&
    sourceDealIds.every((id) => selectedDealIds.includes(id))
  )
}

/** 사전저장부터 서버 apply까지 같은 미팅의 중복 실행을 막습니다. */
export async function runDealGeneration(
  active: Set<string>,
  dealId: string,
  onChange: () => void,
  generate: () => Promise<boolean>,
) {
  if (active.has(dealId)) return false
  active.add(dealId)
  onChange()
  try {
    return await generate()
  } finally {
    active.delete(dealId)
    onChange()
  }
}
