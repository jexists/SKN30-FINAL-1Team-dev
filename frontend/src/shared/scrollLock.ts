/**
 * 뒤 배경의 스크롤을 멈추는 일을 겹쳐 있는 오버레이들이 함께 씁니다.
 *
 * 각자 body 의 overflow 를 되돌리면, 드로어를 닫으면서 모달을 여는 자리처럼 둘의
 * 정리와 준비가 한 커밋에 겹칠 때 늦게 도는 쪽이 먼저 건 잠금을 풀어 버립니다.
 * 그래서 잠근 것을 세어 두고, 마지막 하나가 빠질 때만 원래 값으로 돌립니다.
 */
const locks: symbol[] = []
let previousOverflow = ''

/** 잠그고, 풀 함수를 돌려줍니다. 효과의 정리 단계에서 부르면 됩니다. */
export function lockScroll(): () => void {
  const token = Symbol('scroll-lock')

  if (locks.length === 0) previousOverflow = document.body.style.overflow
  locks.push(token)
  document.body.style.overflow = 'hidden'

  return () => {
    locks.splice(locks.indexOf(token), 1)
    if (locks.length === 0) document.body.style.overflow = previousOverflow
  }
}
