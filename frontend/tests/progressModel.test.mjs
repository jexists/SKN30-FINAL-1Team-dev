import assert from 'node:assert/strict'
import test from 'node:test'

import {
  activityRows,
  progressModel,
} from '../src/pages/Meetings/components/GenerationProgress/progressModel.ts'

test('공통 진행 모델은 미팅·기간 단계와 count·복구 문구를 정확히 매핑한다', () => {
  const cases = [
    // 단계가 오기 전에도 지어낸 "준비 중" 문구 없이 첫 단계가 이미 돌고 있습니다.
    [{ reportKind: 'meeting', progress: null }, '미팅 내용 분석 중', '분석'],
    [
      { reportKind: 'meeting', progress: { stage: 'content_analysis' } },
      '미팅 내용 분석 중',
      '분석',
    ],
    [{ reportKind: 'period', progress: null }, '자료 정리 중', '자료 정리'],
    [
      { reportKind: 'period', progress: { stage: 'report_preparing' } },
      '자료 정리 중',
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
      '보고서 작성 중',
      '작성',
    ],
    // 같은 '작성' 이라도 미팅은 딜마다 한 편씩 씁니다.
    [{ reportKind: 'meeting', progress: { stage: 'report_writing' } }, '딜별 보고서 작성 중', '작성'],
    [
      {
        reportKind: 'period',
        progress: { stage: 'report_revising', recovery_reason: 'valid_draft_fallback' },
      },
      '초안 수정 중',
      '필요 시 수정',
    ],
    [{ reportKind: 'meeting', progress: { stage: 'report_complete' } }, '보고서 마무리 중', '사용자 확인'],
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

test('활동 줄은 지나온 단계만 쌓고 살아 있는 줄은 언제나 하나다', () => {
  // 아직 아무 단계도 오지 않았을 때: 첫 줄 하나뿐입니다.
  const starting = activityRows({ stage: 'starting' }, 'meeting')
  assert.deepEqual(
    starting.map((row) => [row.label, row.state]),
    [['미팅 내용 분석 중', 'live']],
  )

  const writing = activityRows(
    {
      stage: 'report_writing',
      phase_counts: { phase: 'write_initial', total: 2, completed: 1, failed: 0 },
      stage_results: [
        { stage: 'content_analysis', key: 'a', body: '' },
        { stage: 'content_analysis', key: 'b', body: '' },
        { stage: 'prepare', key: 'c', body: '' },
        // 검토·수정은 활동 줄이 아니라 검토 메모로 갑니다.
        { stage: 'review_initial', key: 'd', body: '' },
      ],
    },
    'meeting',
  )
  assert.deepEqual(
    writing.map((row) => row.label),
    ['근거 2건 분류함', '자료 1건 정리함', '딜별 보고서 작성 중'],
  )
  assert.deepEqual(
    writing.map((row) => row.state),
    ['done', 'done', 'live'],
  )
  assert.equal(writing.at(-1).detail, '본문 2개 중 1개 완료')
  assert.equal(writing.filter((row) => row.state === 'live').length, 1)

  // 아직 오지 않은 단계는 내보내지 않습니다.
  assert.ok(!writing.some((row) => row.label.includes('검토')))

  // 검토 횟수는 살아 있는 줄의 부연으로만 붙습니다.
  const review = activityRows({ stage: 'report_review', review_attempt: 1, review_limit: 2 }, 'meeting')
  assert.equal(review.at(-1).label, '근거·표현 검토 중')
  assert.equal(review.at(-1).detail, '검토 1/2회')
  assert.equal(review.filter((row) => row.state === 'live').length, 1)

  // 곁일은 단계 뒤에 붙고, live 를 뺏지 않습니다.
  const withExtras = activityRows({ stage: 'report_writing' }, 'meeting', [
    { key: 'ml', label: '성사 가능성 분석 중', state: 'running' },
  ])
  assert.equal(withExtras.at(-1).label, '성사 가능성 분석 중')
  assert.equal(withExtras.filter((row) => row.state === 'live').length, 1)

  // 기간 보고서는 '자료 정리' 가 제 단계라 따로 접어 넣지 않습니다.
  const period = activityRows(
    { stage: 'report_writing', stage_results: [{ stage: 'prepare', key: 'p', body: '' }] },
    'period',
  )
  assert.deepEqual(
    period.map((row) => row.label),
    ['자료 정리함', '보고서 작성 중'],
  )
})
