import { useEffect, useState } from 'react'

/**
 * 값이 잠잠해진 뒤에만 따라오는 사본입니다.
 *
 * 검색 입력을 그대로 서버에 흘리면 글자마다 요청이 나갑니다. 타이핑이 멈춘 뒤 한 번만
 * 부르려고 둡니다. 요청 취소는 부르는 쪽이 AbortController 로 따로 합니다.
 */
export default function useDebouncedValue<T>(value: T, delay = 250): T {
  const [settled, setSettled] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return settled
}
