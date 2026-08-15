import { BrowserRouter, Navigate, Route, Routes } from 'react-router'

import ManagerRoute from '@/auth/ManagerRoute'
import ProtectedRoute from '@/auth/ProtectedRoute'
import SessionProvider from '@/auth/SessionProvider'
import AppShell from '@/components/layout/AppShell'
import { ROUTES } from '@/constants/routes'
import Calendar from '@/pages/Calendar'
import Complaints from '@/pages/Complaints'
import Contracts, { ContractBoard, ContractDetail, ContractNew } from '@/pages/Contracts'
import Customers from '@/pages/Customers'
import Daily, { DailyCompose, DailyDetail } from '@/pages/Daily'
import Dashboard from '@/pages/Dashboard'
import Documents from '@/pages/Documents'
import Login from '@/pages/Login'
import { MeetingCompose, MeetingDetail } from '@/pages/Meetings'
import NotFound from '@/pages/NotFound'
import Orders, { OrderDetail, OrderNew } from '@/pages/Orders'
import Sales from '@/pages/Sales'
import Team from '@/pages/Team'

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
              <Route path={ROUTES.COMPLAINTS} element={<Complaints />} />

              {/* 팀장만 들어갈 수 있는 화면. 팀원이 주소를 직접 치면 대시보드로 돌아갑니다. */}
              <Route element={<ManagerRoute />}>
                <Route path={ROUTES.TEAM} element={<Team />} />
              </Route>

              <Route path={ROUTES.CALENDAR} element={<Calendar />} />

              {/* 미팅보고서는 일정 하나를 기록하는 화면이라 목록이 없습니다.
                  진입은 대시보드 일정 드로어에서 합니다. */}
              <Route path={ROUTES.MEETINGS}>
                <Route path="new" element={<MeetingCompose />} />
                <Route path=":reportId" element={<MeetingDetail />} />
              </Route>

              {/* 업무 보고는 목록·작성·상세가 한 기능이라 경로를 묶어 둡니다.
                  고정 경로를 :reportId 위에 둡니다. */}
              <Route path={ROUTES.DAILY}>
                <Route index element={<Daily />} />
                <Route path="new" element={<DailyCompose />} />
                {/* 이력은 목록 화면으로 합쳤습니다. 예전 링크만 받아 넘깁니다. */}
                <Route path="history" element={<Navigate to={ROUTES.DAILY} replace />} />
                <Route path=":reportId" element={<DailyDetail />} />
              </Route>

              <Route path={ROUTES.SALES} element={<Sales />} />
              <Route path={ROUTES.DOCUMENTS} element={<Documents />} />

              {/* 계약은 목록·보드·작성·상세가 한 기능이라 경로를 묶어 둡니다.
                  고정 경로를 :contractNo 위에 둡니다. */}
              <Route path={ROUTES.CONTRACTS}>
                <Route index element={<Contracts />} />
                <Route path="board" element={<ContractBoard />} />
                <Route path="new" element={<ContractNew />} />
                <Route path=":contractNo" element={<ContractDetail />} />
              </Route>

              {/* 발주도 목록·작성·상세가 한 기능이라 경로를 묶어 둡니다.
                  고정 경로를 :orderNo 위에 둡니다. */}
              <Route path={ROUTES.ORDERS}>
                <Route index element={<Orders />} />
                <Route path="new" element={<OrderNew />} />
                <Route path=":orderNo" element={<OrderDetail />} />
              </Route>

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
