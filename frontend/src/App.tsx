import { BrowserRouter, Route, Routes } from 'react-router'

import ProtectedRoute from '@/auth/ProtectedRoute'
import SessionProvider from '@/auth/SessionProvider'
import AppShell from '@/components/layout/AppShell'
import { ROUTES } from '@/constants/routes'
import Calendar from '@/pages/Calendar'
import Customers from '@/pages/Customers'
import Dashboard from '@/pages/Dashboard'
import Login from '@/pages/Login'
import NotFound from '@/pages/NotFound'

export default function App() {
  return (
    <BrowserRouter>
      <SessionProvider>
        <Routes>
          <Route path={ROUTES.LOGIN} element={<Login />} />

          <Route element={<ProtectedRoute />}>
            {/* 404 도 셸 안에 둡니다. 사이드바가 남아 있어야 바로 다른 메뉴로 옮겨갈 수 있습니다. */}
            <Route element={<AppShell />}>
              <Route path={ROUTES.DASHBOARD} element={<Dashboard />} />
              <Route path={ROUTES.CUSTOMERS} element={<Customers />} />
              <Route path={ROUTES.CALENDAR} element={<Calendar />} />

              {/* 나머지 메뉴는 아직 라우트가 없어 여기로 떨어집니다.
                  화면을 구현하면 위에 <Route> 한 줄을 추가하세요. */}
              <Route path="*" element={<NotFound />} />
            </Route>
          </Route>
        </Routes>
      </SessionProvider>
    </BrowserRouter>
  )
}
