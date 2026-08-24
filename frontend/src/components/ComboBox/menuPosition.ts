/**
 * 목록을 띄울 화면 좌표입니다.
 *
 * 모달 본문은 overflow: auto, 다이얼로그는 overflow: hidden 이라 목록을 흐름 안에 두면
 * 잘립니다. body 로 꺼내 좌표로 띄우는 대신 위치를 여기서 잽니다. 아래 공간이 좁으면
 * 위로 뒤집습니다. 좌표는 열 때 한 번만 재므로, 열어 둔 채 본문을 스크롤하면 제자리에 남습니다.
 */
export default function menuPosition(box: HTMLElement | null): React.CSSProperties | undefined {
  const rect = box?.getBoundingClientRect()
  if (!rect) return undefined

  const roomBelow = window.innerHeight - rect.bottom
  return {
    left: rect.left,
    width: rect.width,
    ...(roomBelow < 200 ? { bottom: window.innerHeight - rect.top + 4 } : { top: rect.bottom + 4 }),
  }
}
