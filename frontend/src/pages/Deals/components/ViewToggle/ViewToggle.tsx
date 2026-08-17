// 같은 영업 딜을 목록으로 볼지 보드로 볼지 고르는 자리입니다.
// 두 화면이 같은 상태를 보므로 조건은 그대로 두고 보는 방식만 바꿉니다.
//
// 보는 방식이 주소에 들어 있어(/deals · /deals/board) 버튼이 아니라 링크입니다.
import { ColumnsIcon, ListIcon } from '@/components/icons'
import Tabs, { type TabItem } from '@/components/Tabs'
import { ROUTES, dealBoardPath } from '@/constants/routes'
import { useLocation } from 'react-router'

interface Props {
  view: 'list' | 'board'
}

export default function ViewToggle({ view }: Props) {
  const { search } = useLocation()
  const views: TabItem[] = [
    {
      value: 'list',
      label: '리스트',
      to: ROUTES.DEALS + search,
      icon: <ListIcon width={14} height={14} />,
    },
    {
      value: 'board',
      label: '보드',
      to: dealBoardPath() + search,
      icon: <ColumnsIcon width={14} height={14} />,
    },
  ]
  return <Tabs variant="segmented" items={views} value={view} label="보기 방식" />
}
