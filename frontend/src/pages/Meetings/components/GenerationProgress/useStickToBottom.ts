import { useEffect, useRef } from 'react'

// 글이 자라 잠깐 화면 밖으로 밀린 것을 '올려 읽는 중'으로 읽지 않기 위한 여유입니다.
const SLACK_PX = 120

/** 이 요소를 실제로 굴리는 상자. 창이 구르면 null 이고, 그것이 곧 관찰 기준입니다. */
function scrollParent(node: HTMLElement): HTMLElement | null {
  for (let el: HTMLElement | null = node; el; el = el.parentElement) {
    if (/auto|scroll|overlay/.test(getComputedStyle(el).overflowY)) return el
  }
  return null
}

/**
 * 흘러나오는 동안 바닥을 따라갑니다. 돌려주는 ref 는 스크롤 상자의 마지막 자식에 답니다.
 * 사용자가 올려 읽는 중이면 멈추고, 다시 바닥까지 내리면 알아서 재개합니다.
 */
export default function useStickToBottom(active: boolean) {
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const mark = end.current
    const box = mark?.parentElement
    if (!active || !mark || !box) return

    /*
     * 바닥 표식이 보이는가로만 판단합니다. 기준은 구르는 상자 자체입니다 — 창을 기준으로
     * 삼으면 상자가 화면에 다 들어와 있을 때만 맞습니다. root 가 null 이면 창이 기준입니다.
     *
     * ponytail: 기준은 붙을 때 한 번 정합니다. 생성 도중 창을 $bp-lg 경계 너머로 늘였다
     * 줄이면 기준이 옛 상자로 남아 '올려 읽는 중'을 놓칩니다 — 늘 따라가는 쪽으로만
     * 틀리므로 그대로 둡니다. 문제가 되면 resize 에서 다시 걸면 됩니다.
     */
    let stick = true
    const watch = new IntersectionObserver(([entry]) => (stick = entry.isIntersecting), {
      root: scrollParent(box),
      rootMargin: `0px 0px ${SLACK_PX}px 0px`,
    })
    watch.observe(mark)

    /*
     * 진행 데이터가 아니라 실제로 자란 글자를 봅니다 — 본문은 useStreamedText 가 24ms
     * 마다 조금씩 드러내므로 서버 응답에 맞춰서는 따라갈 수 없습니다. smooth 는 쓰지
     * 않습니다. 매끄럽게 흐르는 글에 걸면 애니메이션이 서로 밀립니다.
     */
    const grow = new MutationObserver(() => {
      if (stick) mark.scrollIntoView({ block: 'end' })
    })
    grow.observe(box, { childList: true, subtree: true, characterData: true })

    return () => {
      watch.disconnect()
      grow.disconnect()
    }
  }, [active])

  return end
}
