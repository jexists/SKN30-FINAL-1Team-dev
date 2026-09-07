// 표 한 벌이 들어설 자리입니다. 목록이 이미 서 있는데 조건이 바뀌어 다시 받아 올 때,
// 표 자리만 이것으로 바꿉니다. 툴바·탭·페이지네이션은 자기 자리를 지킵니다.
//
// 첫 진입의 ListPageSkeleton 과 같은 모양(머리글 + 줄 수 만큼의 높이, 카드 모서리)입니다.
// 한 화면이 기다림을 두 가지 방식으로 말하지 않게 하려는 것입니다.
import Skeleton from './Skeleton'
import { tableHeight } from './metrics'

interface Props {
  /** 화면 낭독기가 무엇을 기다리는지 한 번만 읽습니다. */
  label: string
  /** 지금 화면에 서 있는 줄 수. 같은 값을 넘겨야 자리표시자를 걷을 때 화면이 밀리지 않습니다. */
  rows?: number
  className?: string
}

export default function TableSkeleton({ label, rows = 8, className }: Props) {
  return (
    <div className={className} role="status">
      <span className="sr-only">{label}</span>
      <Skeleton height={tableHeight(rows)} radius="var(--r-lg)" />
    </div>
  )
}
