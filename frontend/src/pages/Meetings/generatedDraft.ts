import { messageForCode } from '../../api/errorMessage.ts'
import type { DealAssessment, MeetingProcessingOutput } from '@/types'

export const isInsufficientDealPrediction = (error: string | null | undefined) =>
  error === 'deal_prediction_insufficient_features'

/** 내부 오류 코드는 공용 표로 바꾸고, 이미 사람이 쓴 문구는 그대로 둡니다. */
export function meetingAnalysisErrorMessage(error: unknown): string | undefined {
  if (typeof error !== 'string' || !error) return undefined
  return messageForCode(error, error)
}

/** 저장된 서버 분석을 읽습니다. ML 실패를 새로고침 후 대기로 숨기지 않습니다. */
export function readMeetingAnalysis(value: Record<string, unknown>) {
  const rawStatus = value.analysis_status
  const analysisStatus: 'pending' | 'completed' | 'failed' | undefined =
    rawStatus === 'pending' || rawStatus === 'completed' || rawStatus === 'failed'
      ? rawStatus
      : undefined
  const assessment = value.deal_assessment as Partial<DealAssessment> | null | undefined
  return {
    ...(analysisStatus ? { analysisStatus } : {}),
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
      meetingAnalysisErrorMessage(value.analysis_error) ??
      (analysisStatus === 'failed'
        ? meetingAnalysisErrorMessage('meeting_analysis_failed')
        : undefined),
    reportError:
      typeof value.report_error === 'string' && value.report_error ? value.report_error : undefined,
  }
}

/** AgentRun 후보에서 한 딜의 본문과 ML 결과를 같은 ID로 꺼냅니다. */
export function generatedDealOf(output: MeetingProcessingOutput, dealId: string) {
  const analysis = output.analyses.find((item) => item.sales_deal_id === dealId)
  return {
    report: output.reports?.deal_reports.find((item) => item.sales_deal_id === dealId),
    assessment: analysis?.assessment ?? undefined,
    analysisError: meetingAnalysisErrorMessage(analysis?.error),
  }
}
