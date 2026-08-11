import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'

// 포인터 이벤트로 직접 만든 드래그입니다. HTML5 의 draggable 은 쓰지 않습니다.
//
// 네이티브 드래그는 마우스 제스처 계열 브라우저 확장이 가로채면 dragstart 조차
// 오지 않아 아무 일도 일어나지 않고, 터치 기기에서는 아예 동작하지 않습니다.
// pointerdown/move/up 은 그런 사정이 없어 마우스·터치·펜에서 모두 같게 동작합니다.

export interface Dragging {
  kind: 'event' | 'suggestion'
  id: string
  /** 끌고 다니는 동안 손끝에 붙어 보일 글자 */
  label: string
}

/** 이만큼 움직이기 전에는 드래그로 보지 않습니다. 클릭이 드래그로 오해받지 않게 합니다. */
const THRESHOLD = 4

/** 놓을 자리를 찾을 때 쓰는 표식. 날짜 칸이 이 속성을 답니다. */
export const CELL_ATTR = 'data-cell-iso'

function cellAt(x: number, y: number): string | null {
  const el = document.elementFromPoint(x, y) as HTMLElement | null
  return el?.closest(`[${CELL_ATTR}]`)?.getAttribute(CELL_ATTR) ?? null
}

interface Pending {
  dragging: Dragging
  x: number
  y: number
}

export default function usePointerDrag(onDrop: (dragging: Dragging, dateISO: string) => void) {
  const [dragging, setDragging] = useState<Dragging | null>(null)
  const [dropISO, setDropISO] = useState<string | null>(null)
  const [point, setPoint] = useState<{ x: number; y: number } | null>(null)

  // 누르기만 하고 아직 움직이지 않은 상태. 문턱을 넘으면 dragging 으로 승격합니다.
  const pending = useRef<Pending | null>(null)
  const active = useRef(false)

  const start = useCallback((event: ReactPointerEvent, target: Dragging) => {
    // 왼쪽 버튼(또는 터치)만 받습니다. 오른쪽 클릭으로 끌리면 곤란합니다.
    if (event.button !== 0) return
    pending.current = { dragging: target, x: event.clientX, y: event.clientY }
  }, [])

  useEffect(() => {
    const onMove = (event: PointerEvent) => {
      const held = pending.current
      if (!held) return

      if (!active.current) {
        const far =
          Math.abs(event.clientX - held.x) >= THRESHOLD ||
          Math.abs(event.clientY - held.y) >= THRESHOLD
        if (!far) return
        active.current = true
        setDragging(held.dragging)
      }

      // 터치에서 스크롤로 넘어가지 않게 막습니다. (passive: false 로 등록해야 먹힙니다.)
      event.preventDefault()
      setPoint({ x: event.clientX, y: event.clientY })
      setDropISO(cellAt(event.clientX, event.clientY))
    }

    const finish = (commit: boolean, event?: PointerEvent) => {
      const held = pending.current
      pending.current = null

      if (active.current) {
        // 끌고 나면 곧바로 click 이 따라옵니다. 그대로 두면 놓자마자 상세가 열립니다.
        //
        // 다만 시작점과 끝점이 다른 요소면 click 이 아예 오지 않기도 합니다.
        // once 만 걸어 두면 그 리스너가 남아 다음에 오는 진짜 클릭을 삼켜 버리므로,
        // 오든 안 오든 이번 차례가 끝나면 반드시 걷어냅니다.
        document.addEventListener('click', swallowClick, { capture: true, once: true })
        setTimeout(() => document.removeEventListener('click', swallowClick, true), 0)

        if (commit && held && event) {
          const iso = cellAt(event.clientX, event.clientY)
          if (iso) onDrop(held.dragging, iso)
        }
      }

      active.current = false
      setDragging(null)
      setDropISO(null)
      setPoint(null)
    }

    const swallowClick = (event: MouseEvent) => {
      event.stopPropagation()
      event.preventDefault()
    }

    const onUp = (event: PointerEvent) => finish(true, event)
    const onCancel = () => finish(false)
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') finish(false)
    }

    document.addEventListener('pointermove', onMove, { passive: false })
    document.addEventListener('pointerup', onUp)
    document.addEventListener('pointercancel', onCancel)
    document.addEventListener('keydown', onKeyDown)

    return () => {
      document.removeEventListener('pointermove', onMove)
      document.removeEventListener('pointerup', onUp)
      document.removeEventListener('pointercancel', onCancel)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [onDrop])

  return { dragging, dropISO, point, start }
}
