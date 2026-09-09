import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const vite = await createServer({
  server: { middlewareMode: true, hmr: false },
  define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('http://synthetic.invalid') },
})
after(() => vite.close())

const { summaryWithoutHiddenSections } = await vite.ssrLoadModule('/src/shared/documentSummary.ts')
const { default: ReportBody } = await vite.ssrLoadModule('/src/components/ReportBody.tsx')

const SUMMARY = [
  '# 문서 요약',
  '',
  '## 핵심 요약',
  '계약 조건과 금액이 기재되어 있습니다.',
  '',
  '## 주요 내용',
  '',
  '- LP1500은 수량 5로 기재되어 있습니다.',
  '',
  '## 추출 필드',
  '',
  '- 내부용 값이라 화면에서는 감춥니다.',
  '',
  '## 출처',
  '',
  '- page 3',
].join('\n')

// 마크다운은 앞 공백 세 칸까지와 뒤에 붙는 닫는 # 을 모두 제목으로 인정한다.
const SUMMARY_WITH_HEADING_VARIANTS = [
  '  # 문서 요약',
  '',
  '## 핵심 요약',
  '계약 조건이 기재되어 있습니다.',
  '',
  '  ## 추출 필드',
  '',
  '- 앞 공백이 있는 제목',
  '',
  '## 출처 ##',
  '',
  '- 닫는 샵이 있는 제목',
].join('\n')

test('제목 변형(앞 공백·닫는 샵)에서도 숨김 섹션을 제거한다', () => {
  const visible = summaryWithoutHiddenSections(SUMMARY_WITH_HEADING_VARIANTS)

  assert.ok(visible.includes('## 핵심 요약'))
  assert.ok(visible.includes('계약 조건이 기재되어 있습니다.'))
  assert.ok(!visible.includes('문서 요약'))
  assert.ok(!visible.includes('추출 필드'))
  assert.ok(!visible.includes('앞 공백이 있는 제목'))
  assert.ok(!visible.includes('출처'))
  assert.ok(!visible.includes('닫는 샵이 있는 제목'))
})

test('구버전 요약의 제목과 내부 섹션은 화면에서 감춘다', () => {
  const visible = summaryWithoutHiddenSections(SUMMARY)

  assert.ok(visible.includes('## 핵심 요약'))
  assert.ok(visible.includes('## 주요 내용'))
  assert.ok(visible.includes('- LP1500은 수량 5로 기재되어 있습니다.'))
  // 제목과 내부 섹션은 자료실 드로어에서도 보이지 않는다.
  assert.ok(!visible.includes('# 문서 요약'))
  assert.ok(!visible.includes('## 추출 필드'))
  assert.ok(!visible.includes('## 출처'))
  assert.ok(!visible.includes('page 3'))
})

test('자료요약은 마크다운 기호가 아니라 서식으로 그려진다', () => {
  // 브리핑이 원문을 <pre> 로 흘렸을 때 `## 핵심 요약` 이 글자 그대로 보였다.
  const html = renderToStaticMarkup(
    createElement(ReportBody, { body: summaryWithoutHiddenSections(SUMMARY) }),
  )

  assert.ok(!html.includes('## 핵심 요약'), '마크다운 기호가 그대로 남으면 안 된다')
  assert.ok(html.includes('핵심 요약'))
  assert.ok(html.includes('LP1500'))
})
