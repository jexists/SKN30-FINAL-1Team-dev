/*
 * 브리핑이 화면에 서는 순서와 속도.
 *
 * 본문은 서버에서 **다 만들어진 채로 한 번에** 옵니다(보고서처럼 토큰이 흘러오지 않습니다).
 * 그래서 남은 양에 비례해 드러내는 useStreamedText 를 쓰면 몇 백 자가 몇 프레임 안에 다 서서
 * 문단이 통째로 튀어나옵니다. 여기서는 챗봇 답변처럼 한 글자씩 치고, 한 조각을 다 치면 그
 * 다음 조각(제안 → 위험 → 확인이 필요한 정보)을 차례로 붙입니다.
 *
 * 순서·전이·파생값만 모아 둔 곳입니다. React 를 쓰지 않으므로 그대로 테스트합니다
 * (tests/briefingReveal.test.mjs).
 */

/** 한 번에 치는 글자 수와 그 간격. 둘을 곱하면 초당 약 55자입니다. */
export const TICK_MS = 36
export const CHARS_PER_TICK = 2
/** 문장 끝에서 쉬는 시간. 쉬는 자리가 없으면 한 덩어리로 읽힙니다. */
export const SENTENCE_MS = 260
/** 같은 덩어리 안에서 조각 하나가 붙는 간격(제안 한 줄, 확인 정보 한 줄). */
export const PIECE_MS = 200
/** 덩어리가 바뀌는 자리 — 다 쓴 문단이 자리를 잡을 틈입니다. */
export const BLOCK_MS = 320
/** 위험 표시는 글이 아니라 알약이라 더 촘촘히 붙습니다. */
export const CHIP_MS = 120

export interface RevealBlock {
  title: string
  body: string
  actions: string[]
}

export interface RevealInput {
  blocks: RevealBlock[]
  risks: string[]
  missingInformation: string[]
}

/**
 * 화면에 설 조각 하나. 글줄(제목·본문·제안·확인이 필요한 정보)은 글자 단위로 쳐지고,
 * 위험 표시는 글줄이 아니라 알약이라 통째로 섭니다.
 */
export type Step =
  | { kind: 'title' | 'body'; block: number; text: string }
  | { kind: 'action'; block: number; index: number; text: string }
  | { kind: 'missing'; index: number; text: string }
  | { kind: 'risk'; index: number }

/** 몇 번째 조각의 몇 글자까지 왔는지. */
export interface RevealState {
  step: number
  chars: number
}

export const START: RevealState = { step: 0, chars: 0 }

/** 다 선 상태. 흐르지 않을 때(이미 있던 브리핑을 그냥 열 때)는 여기서 시작합니다. */
export function endState(steps: Step[]): RevealState {
  return { step: steps.length, chars: 0 }
}

/** 조각을 설 순서대로 폅니다. 빈 글은 조각이 되지 않습니다 — 빈 줄을 치고 있을 수는 없습니다. */
export function revealSteps({ blocks, risks, missingInformation }: RevealInput): Step[] {
  const steps: Step[] = []
  blocks.forEach((block, index) => {
    if (block.title) steps.push({ kind: 'title', block: index, text: block.title })
    if (block.body) steps.push({ kind: 'body', block: index, text: block.body })
    block.actions.forEach((action, order) => {
      if (action) steps.push({ kind: 'action', block: index, index: order, text: action })
    })
  })
  risks.forEach((risk, index) => {
    if (risk) steps.push({ kind: 'risk', index })
  })
  missingInformation.forEach((information, index) => {
    if (information) steps.push({ kind: 'missing', index, text: information })
  })
  return steps
}

/**
 * 문장이 끝나는 자리. 브리핑 본문에는 줄바꿈이 거의 없어 문장 부호로 끊습니다. 마지막
 * 문장의 끝(글 전체의 끝)은 쉬는 자리가 아니라 조각이 끝나는 자리라 넣지 않습니다.
 *
 * 마침표 뒤에 공백이나 글 끝이 와야 문장이 끝난 것으로 봅니다. 영업 브리핑에는 마침표가
 * 문장 부호가 아닌 자리에 늘 섞여 들어옵니다 — 금액(12,500.50), 날짜(3.10), 단가(1.5억),
 * 파일명(계약서.pdf). 이 조건이 없으면 숫자 한가운데서 끊겨, 타자가 거기서 쉬고 형광펜도
 * 거기서 잘립니다(briefingCitations 가 이 자리를 문장 경계로 씁니다).
 */
export function sentenceEnds(text: string): number[] {
  const ends: number[] = []
  const finder = /[.!?。]["'”’)\]]*(?:\s+|$)|\n+/g
  let match: RegExpExecArray | null
  while ((match = finder.exec(text))) {
    const end = match.index + match[0].length
    if (end < text.length) ends.push(end)
  }
  return ends
}

function typed(step: Step): step is Extract<Step, { text: string }> {
  return step.kind !== 'risk'
}

/** 어느 덩어리에 속한 조각인지. 덩어리가 바뀌는 자리에서 한 박자 쉽니다. */
function groupOf(step: Step): string {
  if (step.kind === 'risk') return 'risk'
  if (step.kind === 'missing') return 'missing'
  return `block:${step.block}`
}

/** 다음 조각이 서기 전에 기다리는 시간. */
function delayBefore(steps: Step[], index: number): number {
  const next = steps[index]
  const previous = steps[index - 1]
  if (!next || !previous) return BLOCK_MS
  if (groupOf(next) !== groupOf(previous)) return BLOCK_MS
  if (next.kind === 'risk') return CHIP_MS
  return PIECE_MS
}

/**
 * 다음 상태와, 그 상태가 되기까지 기다릴 시간. 더 설 것이 없으면 null.
 *
 * 글자를 치는 중이면 한 틱만큼 더 치고(문장 끝에 닿아 있으면 그만큼 쉬었다가), 다 쳤으면
 * 다음 조각으로 넘어갑니다. 통째로 서는 조각은 그 자리에 서 있는 동안이 곧 간격입니다.
 */
export function advance(
  steps: Step[],
  state: RevealState,
): { state: RevealState; delay: number } | null {
  const step = steps[state.step]
  if (!step) return null
  if (typed(step) && state.chars < step.text.length) {
    const paused = state.chars > 0 && sentenceEnds(step.text).includes(state.chars)
    return {
      state: { step: state.step, chars: Math.min(step.text.length, state.chars + CHARS_PER_TICK) },
      delay: paused ? SENTENCE_MS : TICK_MS,
    }
  }
  return {
    state: { step: state.step + 1, chars: 0 },
    delay: delayBefore(steps, state.step + 1),
  }
}

/**
 * 화면에 선 글줄 하나. `done` 이 false 인 줄이 지금 쳐지고 있는 줄이고, 그런 줄은 한 번에
 * 하나뿐입니다 — 캐럿도 목록의 점도 이 값 하나로 정해집니다.
 */
export interface RevealedLine {
  text: string
  done: boolean
}

export interface RevealedBlock {
  title: RevealedLine
  body: RevealedLine
  /** 여기까지 붙은 제안. 아직 오지 않은 줄은 배열에 없습니다. */
  actions: RevealedLine[]
}

export interface RevealedView {
  /** 앞에서부터 드러난 덩어리들. 아직 오지 않은 덩어리는 배열에 없습니다. */
  blocks: RevealedBlock[]
  risks: number
  missing: RevealedLine[]
  done: boolean
}

const EMPTY: RevealedLine = { text: '', done: true }

/** 지금 상태에서 화면이 그릴 것만 뽑습니다. */
export function revealView(steps: Step[], state: RevealState): RevealedView {
  const blocks: RevealedBlock[] = []
  const missing: RevealedLine[] = []
  let risks = 0
  steps.forEach((step, index) => {
    if (index > state.step) return
    if (step.kind === 'risk') {
      risks = Math.max(risks, step.index + 1)
      return
    }
    const passed = index < state.step
    const line: RevealedLine = {
      text: passed ? step.text : step.text.slice(0, state.chars),
      done: passed || state.chars >= step.text.length,
    }
    // 조각은 이미 설 순서대로 펴져 있으므로 자리를 따지지 않고 이어 붙입니다. 빈 글은
    // 조각이 되지 않아 배열에 구멍이 생기지 않습니다.
    if (step.kind === 'missing') {
      missing.push(line)
      return
    }
    while (blocks.length <= step.block) {
      blocks.push({ title: EMPTY, body: EMPTY, actions: [] })
    }
    const block = blocks[step.block]
    if (step.kind === 'title') block.title = line
    else if (step.kind === 'body') block.body = line
    else block.actions.push(line)
  })
  return { blocks, risks, missing, done: state.step >= steps.length }
}
