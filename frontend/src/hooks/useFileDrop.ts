import { useState, type DragEvent } from 'react'

// 바깥(탐색기·바탕화면)에서 끌어온 파일을 받는 자리입니다. 화면 안의 카드를 옮기는
// usePointerDrag 와는 다른 일이라 네이티브 드래그 이벤트를 씁니다.

/**
 * @param onFiles 놓인 파일. 형식·용량 검사는 호출부가 합니다 — 드롭은 input 의 accept 를 거치지 않습니다.
 * @param disabled 올리는 중처럼 받으면 안 될 때. 핸들러가 빠져 브라우저 기본 동작으로 돌아갑니다.
 */
export default function useFileDrop(onFiles: (files: FileList) => void, disabled = false) {
  const [dragging, setDragging] = useState(false)

  if (disabled) return { dragging: false, dropProps: {} }

  const dropProps = {
    onDragOver: (event: DragEvent<HTMLElement>) => {
      // 파일이 아닌 것(글자·링크)을 끌 때는 자리를 밝히지 않습니다.
      if (!event.dataTransfer.types.includes('Files')) return
      // 막지 않으면 drop 이 오지 않고 브라우저가 파일을 새 탭으로 엽니다.
      event.preventDefault()
      setDragging(true)
    },
    onDragLeave: (event: DragEvent<HTMLElement>) => {
      // 자리 안의 글자·아이콘 위로 옮겨 갈 때도 leave 가 납니다. 그때 끄면 깜빡입니다.
      if (event.currentTarget.contains(event.relatedTarget as Node | null)) return
      setDragging(false)
    },
    onDrop: (event: DragEvent<HTMLElement>) => {
      event.preventDefault()
      setDragging(false)
      if (event.dataTransfer.files.length > 0) onFiles(event.dataTransfer.files)
    },
  }

  return { dragging, dropProps }
}
