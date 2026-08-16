// 같은 영업 건을 목록으로 볼지 보드로 볼지 고르는 자리입니다.
// 두 화면이 같은 상태를 보므로 조건은 그대로 두고 보는 방식만 바꿉니다.
import { Link } from 'react-router'

import { ColumnsIcon, ListIcon } from '@/components/icons'
import { ROUTES, visitBoardPath } from '@/constants/routes'

import styles from './ViewToggle.module.scss'

interface Props {
  view: 'list' | 'board'
}

export default function ViewToggle({ view }: Props) {
  return (
    <div className={styles.root} role="group" aria-label="보기 방식">
      <Link
        to={ROUTES.VISITS}
        className={[styles.item, view === 'list' ? styles.isOn : ''].filter(Boolean).join(' ')}
        aria-current={view === 'list' ? 'page' : undefined}
      >
        <ListIcon width={14} height={14} />
        리스트
      </Link>
      <Link
        to={visitBoardPath()}
        className={[styles.item, view === 'board' ? styles.isOn : ''].filter(Boolean).join(' ')}
        aria-current={view === 'board' ? 'page' : undefined}
      >
        <ColumnsIcon width={14} height={14} />
        보드
      </Link>
    </div>
  )
}
