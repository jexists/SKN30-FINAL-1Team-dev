import type { MouseEvent } from 'react'

/**
 * dangerouslySetInnerHTML 로 그린 본문에서 눌린 이미지를 찾습니다. 그 안의 <img> 에는
 * 핸들러를 하나씩 달 수 없어, 감싸는 요소가 클릭을 받아 이 함수에 넘깁니다.
 * 이미지가 아니면 null 입니다.
 */
export function clickedImage(event: MouseEvent): { src: string; alt: string } | null {
  const target = event.target as HTMLElement
  if (target.tagName !== 'IMG') return null

  const image = target as HTMLImageElement
  // 본문 편집기는 사진을 링크로 감싸기도 합니다. 새 탭으로 나가지 않고 여기서 봅니다.
  event.preventDefault()
  return { src: image.currentSrc || image.src, alt: image.alt || '본문 이미지' }
}
