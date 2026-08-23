// 계정 발급 화면의 문지기. 메뉴에 없다는 것만으로는 주소를 직접 친 사람을 막지 못합니다.
//
// 서버도 같은 판단을 합니다. 화면단의 이 검사는 잘못 들어온 사람을 돌려보내는 것이지
// 권한을 지키는 수단이 아닙니다. 실제 근거는 백엔드의 ADMIN_USER_IDS 입니다.
import { Navigate, Outlet } from 'react-router'

import { ROUTES } from '@/constants/routes'

import { useCurrentUser } from './sessionContext'

export default function AdminRoute() {
  const { isAdmin } = useCurrentUser()

  if (!isAdmin) return <Navigate to={ROUTES.DASHBOARD} replace />

  return <Outlet />
}
