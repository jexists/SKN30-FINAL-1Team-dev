import { useCallback, useSyncExternalStore } from 'react'

/**
 * 미디어쿼리 일치 여부를 구독합니다.
 *
 * 레이아웃 자체는 CSS 로 처리하세요. 이 훅은 CSS 로 표현할 수 없는 동작
 * (예: 데스크톱 폭으로 넓어지면 열려 있던 모바일 드로어를 닫기)에만 씁니다.
 */
export default function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      const list = window.matchMedia(query)
      list.addEventListener('change', onStoreChange)
      return () => list.removeEventListener('change', onStoreChange)
    },
    [query],
  )

  return useSyncExternalStore(subscribe, () => window.matchMedia(query).matches)
}
