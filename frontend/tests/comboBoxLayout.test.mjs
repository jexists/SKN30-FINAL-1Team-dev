// combo-box 를 쓰는 입력칸의 레이아웃이 조용히 깨지는 것을 막는 테스트.
//
// 배경: 고른 것을 칩으로 보여 주는 입력칸(담당자·수신자·고객 선택)에서, 칩이 하나만 있어도
// 입력칸이 다음 줄로 밀려 칸이 두 줄로 부푸는 버그가 여러 번 되돌아왔습니다. 원인은 form-field
// 가 폼 안 모든 input 에 건 width: 100% 가 combo-box 안에서 flex-basis 로 새는 것이었고,
// 컴포넌트마다 각자 복사해 둔 덮어쓰기 규칙 중 한쪽만 고쳐지곤 했습니다.
//
// 화면을 실제로 재는 테스트는 아닙니다. node 에는 레이아웃 엔진이 없습니다. 대신 실제로
// 브라우저에 실리는 CSS 를 컴파일해, 그 버그가 성립하기 위한 조건이 되살아났는지를 봅니다.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { pathToFileURL } from 'node:url'

import * as sass from 'sass'

const srcDir = path.resolve(import.meta.dirname, '../src')
const stylesDir = path.join(srcDir, 'styles')

/** vite.config.ts 의 css.preprocessorOptions.scss 와 같은 방식으로 컴파일한다. */
function compile(file) {
  const source = fs.readFileSync(file, 'utf8')
  return sass.compileString(`@use "variables" as *;\n@use "mixins" as *;\n${source}`, {
    loadPaths: [stylesDir],
    url: pathToFileURL(file),
  }).css
}

function scssFilesUnder(dir) {
  return fs
    .readdirSync(dir, { recursive: true })
    .map((name) => path.join(dir, String(name)))
    .filter((file) => file.endsWith('.module.scss'))
}

/** 선택자별 선언 블록으로 쪼갠다. 중첩이 없는 평평한 CSS 라 이 정도로 충분하다. */
function rulesOf(css) {
  return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, selector, body]) => ({
    selector: selector.trim(),
    body: body.trim(),
  }))
}

const comboBoxModules = scssFilesUnder(srcDir).filter((file) =>
  fs.readFileSync(file, 'utf8').includes('@include combo-box'),
)

test('combo-box 를 쓰는 모듈을 실제로 찾아 낸다', () => {
  // 이 목록이 비면 아래 테스트가 아무것도 검사하지 않고 통과해 버린다.
  assert.ok(comboBoxModules.length >= 4, `찾은 모듈: ${comboBoxModules.length}`)
})

for (const file of comboBoxModules) {
  const name = path.basename(file)

  test(`${name}: 안쪽 input 이 폼의 width: 100% 를 물려받지 않는다`, () => {
    const inputRules = rulesOf(compile(file)).filter(
      (rule) => rule.selector.endsWith('input') && rule.body.includes('flex:'),
    )
    assert.ok(inputRules.length > 0, 'combo-box 가 만드는 input 규칙이 있어야 한다')

    for (const rule of inputRules) {
      // width 를 되돌리지 않으면 flex-basis: auto 가 폼이 준 100% 를 읽는다.
      assert.match(rule.body, /width:\s*auto/, `${rule.selector} 에 width: auto 가 없다`)
      // basis 를 auto 로 두면 width 든 input 기본 폭이든 결국 너무 넓어져 줄이 넘어간다.
      assert.doesNotMatch(
        rule.body,
        /flex:\s*\d+\s+\d+\s+auto/,
        `${rule.selector} 의 flex-basis 가 auto 다`,
      )
    }
  })
}

test('칩 줄은 입력칸의 최소 폭을 상속으로 내려 준다', () => {
  const chipModules = comboBoxModules.filter((file) =>
    fs.readFileSync(file, 'utf8').includes('@include combo-chips'),
  )
  assert.ok(chipModules.length >= 2, `칩을 쓰는 모듈: ${chipModules.length}`)

  for (const file of chipModules) {
    const css = compile(file)
    assert.match(
      css,
      /--combo-input-min:\s*\d+px/,
      `${path.basename(file)} 의 칩 줄이 --combo-input-min 을 안 내려 준다`,
    )
  }
})

test('칩 줄 규칙을 컴포넌트가 다시 복사해 두지 않는다', () => {
  // 같은 규칙이 여러 파일에 흩어지면 고칠 때 한쪽만 고쳐진다. 그게 이 버그가 돌아온 경로였다.
  for (const file of comboBoxModules) {
    const source = fs.readFileSync(file, 'utf8')
    if (!source.includes('@include combo-chips')) continue

    const chipsBlock = source.match(/\.chips\s*\{([^}]*)\}/)?.[1] ?? ''
    assert.doesNotMatch(
      chipsBlock,
      /input\s*\{/,
      `${path.basename(file)} 이 칩 입력칸 규칙을 따로 들고 있다. combo-chips 에서 고칠 것`,
    )
  }
})
