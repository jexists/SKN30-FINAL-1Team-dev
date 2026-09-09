/**
 * 겹쳐 있는 오버레이들 중 어느 것이 맨 위인지 함께 봅니다.
 *
 * 일정 모달 위에 고객 등록 모달을 얹거나 드로어 위에 이미지 전체보기를 띄우는 것처럼 두
 * 장이 겹치면, Escape 한 번에 둘 다 닫히고 안쪽 스크림을 눌러도 바깥 핸들러까지 올라갑니다
 * (portal 로 꺼내도 React 이벤트는 컴포넌트 트리를 탑니다). 맨 위의 것만 답하도록,
 * 열려 있는 것을 쌓아 두고 각자 자기가 꼭대기인지 물어봅니다.
 */
const stack: symbol[] = []

/** 얹고, 맨 위인지 묻는 함수와 내리는 함수를 돌려줍니다. 효과에서 열고 닫으면 됩니다. */
export function pushOverlay(): { isTop: () => boolean; release: () => void } {
  const token = Symbol('overlay')

  stack.push(token)

  return {
    isTop: () => stack[stack.length - 1] === token,
    release: () => {
      stack.splice(stack.indexOf(token), 1)
    },
  }
}
