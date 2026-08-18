import { Navigate, Outlet } from 'react-router'

import { ROUTES } from '@/constants/routes'

import { useSession } from './sessionContext'

export default function ProtectedRoute() {
  const { session, status } = useSession()

  // 아직 판정 중입니다. 여기서 로그인으로 보내면 새로고침마다 주소를 잃습니다.
  if (status === 'loading') return null

  // 백엔드 확인 없이 보호 화면을 열지 않습니다. 연결 실패 안내는 모달이 맡습니다.
  if (!session) return <Navigate to={ROUTES.LOGIN} replace />

  return <Outlet />
}
