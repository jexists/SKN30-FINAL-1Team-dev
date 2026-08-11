import { Navigate, Outlet } from 'react-router'

import { ROUTES } from '@/constants/routes'

import { useSession } from './sessionContext'

export default function ProtectedRoute() {
  const { session } = useSession()

  if (!session) return <Navigate to={ROUTES.LOGIN} replace />

  return <Outlet />
}
