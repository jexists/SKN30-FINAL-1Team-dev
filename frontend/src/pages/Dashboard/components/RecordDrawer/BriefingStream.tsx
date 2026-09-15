// 브리핑 본문. 기다린 끝에 도착한 글은 챗봇 답변처럼 한 글자씩 치고, 한 조각을 다 치면
// 그 다음 조각(제안 → 위험 표시 → 확인이 필요한 정보)을 차례로 붙입니다.
//
// 순서와 속도는 briefingReveal.ts 에 있습니다 — 여기서는 그 결과를 그리기만 합니다.
// 블록마다 따로 타이머를 두지 않는 것이 중요합니다. 각자 세면 갱신으로 본문이 바뀌었을 때
// 이미 끝까지 간 상태가 남아 새 브리핑이 통째로 튀어나옵니다.
import { useEffect, useState } from 'react'

import { highlightChecks } from './briefingText'
import {
  START,
  advance,
  endState,
  revealSteps,
  revealView,
  type RevealInput,
  type RevealedLine,
} from './briefingReveal'
import styles from './RecordDrawer.module.scss'

export interface BriefingBlock {
  key: string
  title: string
  body: string
  actions: string[]
}

function reducedMotion() {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * 조각을 하나씩 세웁니다. 타이머는 언제나 하나뿐입니다.
 *
 * 조각과 진행을 한 덩어리로 들고 있습니다. 내용이 바뀌면(서명이 달라지면) 둘을 함께 갈고
 * 처음부터 다시 칩니다 — 갱신이 끝나 새 본문이 들어왔는데 커서가 이전 본문의 끝에 있으면
 * 새 글이 통째로 튀어나옵니다. 폴링이 같은 내용을 다시 실어 오는 것은 서명이 같아 그대로 둡니다.
 */
function useReveal(input: RevealInput, stream: boolean, signature: string) {
  const open = () => {
    const steps = revealSteps(input)
    return { signature, steps, state: stream && !reducedMotion() ? START : endState(steps) }
  }
  const [reveal, setReveal] = useState(open)
  if (reveal.signature !== signature) setReveal(open())

  useEffect(() => {
    const next = advance(reveal.steps, reveal.state)
    if (!next) return
    const timer = setTimeout(
      () => setReveal((current) => ({ ...current, state: next.state })),
      next.delay,
    )
    return () => clearTimeout(timer)
  }, [reveal])

  return reveal
}

/**
 * 글줄 하나. 아직 치는 중이면 끝에 캐럿이 섭니다.
 *
 * @param checks `[[ ]]` 로 표시된 "확인해야 할 값"을 강조할지. 본문에만 씁니다 — 제목과
 *   목록 줄은 마커를 쓰지 않습니다.
 */
function line(shown: RevealedLine, checks = false) {
  return (
    <>
      {checks ? highlightChecks(shown.text) : shown.text}
      {!shown.done && <span className={styles.caret} aria-hidden="true" />}
    </>
  )
}

/**
 * 점이 붙는 목록 줄(제안, 확인이 필요한 정보). 치는 동안에는 점을 감춰 두었다가 줄을 다 친
 * 순간 찍습니다 — 점이 곧 "이 줄은 끝났다"는 표시입니다.
 */
function item(shown: RevealedLine, index: number) {
  return (
    <li key={index} className={shown.done ? '' : styles.typingLine}>
      {line(shown)}
    </li>
  )
}

/**
 * @param stream 기다린 끝에 막 도착한 글인지. false 면 흐르지 않고 그대로 섭니다 —
 *   이미 있던 브리핑을 열 때마다 처음부터 다시 치면 읽던 자리를 잃습니다.
 * @param risks 위험 표시 라벨. 본문이 다 선 뒤에 하나씩 붙습니다.
 * @param missingInformation 확인이 필요한 정보. 마지막으로 한 줄씩 붙습니다.
 */
export default function BriefingStream({
  blocks,
  stream,
  risks,
  missingInformation,
}: {
  blocks: BriefingBlock[]
  stream: boolean
  risks: string[]
  missingInformation: string[]
}) {
  // 내용이 같으면 조각도 그대로여야 타이머가 렌더마다 다시 걸리지 않습니다. 배열 자체는
  // 렌더마다 새로 오므로 값으로 비교합니다.
  const signature = [
    blocks.map((block) => `${block.key}:${block.title}:${block.body}:${block.actions.join('·')}`),
    risks.join(','),
    missingInformation.join('|'),
  ].join('#')
  const reveal = useReveal({ blocks, risks, missingInformation }, stream, signature)
  const view = revealView(reveal.steps, reveal.state)
  // 흐르지 않을 때는 등장 동작도 없습니다. 열자마자 전부 서 있어야 합니다.
  const appear = stream ? styles.appear : ''

  return (
    <>
      {view.blocks.map((shown, index) => (
        <div
          key={blocks[index].key}
          // 문단을 다 친 순간 자리를 잡습니다. 그때부터 제안이 아래에 붙습니다.
          className={`${styles.highlight} ${shown.body.done && stream ? styles.settled : ''}`}
        >
          {shown.title.text && (
            <h4 className={shown.title.done ? '' : styles.typingText}>{line(shown.title)}</h4>
          )}
          {(shown.body.text || !shown.body.done) && (
            <p className={styles.note}>{line(shown.body, true)}</p>
          )}
          {shown.actions.length > 0 && (
            <ul className={styles.actions}>{shown.actions.map(item)}</ul>
          )}
        </div>
      ))}
      {view.risks > 0 && (
        <div className={styles.pills}>
          {risks.slice(0, view.risks).map((risk, index) => (
            <i key={index} className={`${styles.pill} ${appear}`}>
              {risk}
            </i>
          ))}
        </div>
      )}
      {view.missing.length > 0 && (
        <div className={styles.missingInformation}>
          <h4 className={appear}>확인이 필요한 정보</h4>
          <ul className={styles.actions}>{view.missing.map(item)}</ul>
        </div>
      )}
    </>
  )
}
