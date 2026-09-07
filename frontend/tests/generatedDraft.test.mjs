import assert from 'node:assert/strict'
import test from 'node:test'

import {
  generatedDealOf,
  isInsufficientDealPrediction,
  readMeetingAnalysis,
} from '../src/pages/Meetings/generatedDraft.ts'

test('AgentRun 후보는 같은 딜 ID의 본문과 ML 결과를 직접 묶는다', () => {
  const assessment = { label: 'high', high_probability: 0.8, model_version: 'test-v1' }
  const output = {
    reports: {
      deal_reports: [
        { sales_deal_id: 'deal-a', title: '새 제목', body: '새 본문', evidence_ids: ['S0001'] },
      ],
      common_report: null,
      unassigned_report: null,
    },
    analyses: [
      { sales_deal_id: 'deal-a', features: {}, assessment, error: null },
      { sales_deal_id: 'deal-b', features: null, assessment: null, error: '분석 실패' },
    ],
    evidence: { selected_deal_ids: ['deal-a', 'deal-b'] },
    errors: {},
  }

  assert.deepEqual(generatedDealOf(output, 'deal-a'), {
    report: output.reports.deal_reports[0],
    assessment,
    analysisError: undefined,
  })
  assert.deepEqual(generatedDealOf(output, 'deal-b'), {
    report: undefined,
    assessment: undefined,
    analysisError: '분석 실패',
  })
})

test('저장된 ML 태그와 실패 정보를 복원하고 불완전한 결과는 무시한다', () => {
  const assessment = { label: 'high', high_probability: 0.8, model_version: 'test-v1' }
  assert.deepEqual(readMeetingAnalysis({ deal_assessment: assessment }), {
    assessment,
    analysisError: undefined,
    reportError: undefined,
  })
  assert.deepEqual(readMeetingAnalysis({ deal_assessment: null, analysis_error: '분석 실패' }), {
    assessment: undefined,
    analysisError: '분석 실패',
    reportError: undefined,
  })
  assert.equal(
    readMeetingAnalysis({ report_error: '본문 생성 실패' }).reportError,
    '본문 생성 실패',
  )
  assert.equal(readMeetingAnalysis({ deal_assessment: { label: 'high' } }).assessment, undefined)
  assert.equal(isInsufficientDealPrediction('deal_prediction_insufficient_features'), true)
  assert.equal(isInsufficientDealPrediction('deal_prediction_failed'), false)
})
