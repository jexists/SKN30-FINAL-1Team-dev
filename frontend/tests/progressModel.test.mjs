import assert from 'node:assert/strict'
import test from 'node:test'

import { progressModel } from '../src/pages/Meetings/components/GenerationProgress/progressModel.ts'

test('공통 진행 모델은 미팅·기간 단계와 count·복구 문구를 정확히 매핑한다', () => {
  const cases = [
    [{ reportKind: 'meeting', progress: null }, '미팅 처리를 준비하는 중입니다', '분석'],
    [
      { reportKind: 'meeting', progress: { stage: 'content_analysis' } },
      '미팅 내용을 딜별로 나누고 있습니다.',
      '분석',
    ],
    [{ reportKind: 'period', progress: null }, '보고서 자료 정리를 준비하는 중입니다', '자료 정리'],
    [
      { reportKind: 'period', progress: { stage: 'report_preparing' } },
      '보고서를 정리하고 있습니다.',
      '자료 정리',
    ],
    [
      {
        reportKind: 'period',
        progress: {
          stage: 'report_writing',
          phase_counts: { phase: 'synthesize', total: 1, completed: 0, failed: 0 },
        },
      },
      '보고서를 작성하는 중입니다',
      '작성',
    ],
    [
      {
        reportKind: 'period',
        progress: { stage: 'report_revising', recovery_reason: 'valid_draft_fallback' },
      },
      '수정 중인 초안',
      '필요 시 수정',
    ],
    [
      { reportKind: 'meeting', progress: { stage: 'report_complete' } },
      '보고서가 준비되었습니다. 내용을 확인해 주세요.',
      '사용자 확인',
    ],
  ]
  for (const [{ reportKind, progress }, label, step] of cases) {
    const model = progressModel(progress, reportKind)
    assert.equal(model.label, label)
    assert.equal(model.currentStep, step)
    assert.ok(model.steps.includes(model.currentStep))
  }
  assert.equal(
    progressModel(
      {
        stage: 'report_review',
        phase_counts: { phase: 'review_initial', total: 3, completed: 2, failed: 1 },
      },
      'period',
    ).countLabel,
    '검토 3개 중 2개 완료 · 실패 1',
  )
  assert.equal(
    progressModel(
      { stage: 'report_revising', recovery_reason: 'original_source_fallback' },
      'period',
    ).recoveryLabel,
    '일부 자료 요약에 실패해 원문으로 계속 작성합니다.',
  )
  assert.equal(
    progressModel(
      {
        stage: 'report_writing',
        phase_counts: { phase: 'synthesize', total: 0, completed: 0, failed: 0 },
      },
      'period',
    ).countLabel,
    undefined,
  )
  assert.equal(
    progressModel(
      {
        stage: 'report_revising',
        phase_counts: { phase: 'repair', total: 2, completed: 1, failed: 0 },
      },
      'period',
    ).countLabel,
    '본문 2개 중 1개 완료',
  )
})
