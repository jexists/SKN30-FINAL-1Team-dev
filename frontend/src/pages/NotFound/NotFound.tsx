import { useLocation, useNavigate } from 'react-router'

import Button from '@/components/Button'
import { NotFoundIcon } from '@/components/icons'
import { findNavLabel } from '@/constants/navigation'
import { ROUTES } from '@/constants/routes'

import styles from './NotFound.module.scss'

/**
 * 아직 만들지 않은 메뉴와 잘못 입력한 주소를 함께 받습니다.
 *
 * 메뉴에 있는 경로면 "준비 중"임을 밝히고, 그렇지 않으면 없는 주소로 안내합니다.
 * 화면을 구현하면 App.tsx 에 <Route> 를 추가하는 것만으로 여기서 빠집니다.
 */
export default function NotFound() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const plannedLabel = findNavLabel(pathname)

  return (
    <section className={styles.root}>
      <NotFoundIcon width={40} height={40} />
      <p className={styles.eyebrow}>404</p>
      <h1 className={styles.title}>{plannedLabel ?? '페이지를 찾을 수 없습니다'}</h1>
      <p className={styles.copy}>해당하는 화면이 없습니다.</p>
      <Button variant="outline" onClick={() => void navigate(ROUTES.DASHBOARD)}>
        대시보드로 돌아가기
      </Button>
    </section>
  )
}
