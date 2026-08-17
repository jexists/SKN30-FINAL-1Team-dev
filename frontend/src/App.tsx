import { BrowserRouter, Navigate, Route, Routes } from 'react-router'

import ManagerRoute from '@/auth/ManagerRoute'
import ProtectedRoute from '@/auth/ProtectedRoute'
import SessionProvider from '@/auth/SessionProvider'
import AppShell from '@/components/layout/AppShell'
import { ROUTES } from '@/constants/routes'
import Calendar from '@/pages/Calendar'
import Complaints from '@/pages/Complaints'
import Contracts from '@/pages/Contracts'
import Customers from '@/pages/Customers'
import Daily, { DailyCompose, DailyDetail, DailyMeetingPick } from '@/pages/Daily'
import Dashboard from '@/pages/Dashboard'
import Documents from '@/pages/Documents'
import LegalDoc from '@/pages/Legal'
import Login from '@/pages/Login'
import { MeetingCompose, MeetingDetail } from '@/pages/Meetings'
import MyPage from '@/pages/MyPage'
import NotFound from '@/pages/NotFound'
import Notifications from '@/pages/Notifications'
import Orders, { OrderDetail, OrderNew } from '@/pages/Orders'
import Quotes from '@/pages/Quotes'
import Sales from '@/pages/Sales'
import Team from '@/pages/Team'
import Deals, { DealBoard } from '@/pages/Deals'

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

              {/* 알림은 사이드바에 없습니다. 진입은 헤더 벨에서만 합니다. */}
              <Route path={ROUTES.NOTIFICATIONS} element={<Notifications />} />

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
                {/* 미팅보고서는 일정 하나에 붙습니다. 어느 일정인지 여기서 고릅니다. */}
                <Route path="pick" element={<DailyMeetingPick />} />
                {/* 이력은 목록 화면으로 합쳤습니다. 예전 링크만 받아 넘깁니다. */}
                <Route path="history" element={<Navigate to={ROUTES.DAILY} replace />} />
                <Route path=":reportId" element={<DailyDetail />} />
              </Route>

              <Route path={ROUTES.SALES} element={<Sales />} />
              <Route path={ROUTES.DOCUMENTS} element={<Documents />} />

              {/* 영업 현황은 같은 딜을 목록과 보드 두 가지로 봅니다. */}
              <Route path={ROUTES.DEALS}>
                <Route index element={<Deals />} />
                <Route path="board" element={<DealBoard />} />
              </Route>

              <Route path={ROUTES.QUOTES} element={<Quotes />} />

              <Route path={ROUTES.CONTRACTS} element={<Contracts />} />
              <Route
                path={`${ROUTES.CONTRACTS}/*`}
                element={<Navigate to={ROUTES.CONTRACTS} replace />}
              />

              {/* 발주도 목록·작성·상세가 한 기능이라 경로를 묶어 둡니다.
                  고정 경로를 :orderNo 위에 둡니다. */}
              <Route path={ROUTES.ORDERS}>
                <Route index element={<Orders />} />
                <Route path="new" element={<OrderNew />} />
                <Route path=":orderNo" element={<OrderDetail />} />
              </Route>

              {/* 마이페이지는 사이드바에 없습니다. 진입은 사이드바 하단 이름과
                  헤더 아바타에서 합니다. 약관 세 화면은 여기서만 들어갑니다. */}
              <Route path={ROUTES.MYPAGE}>
                <Route index element={<MyPage />} />
                <Route path="terms" element={<LegalDoc doc="terms" />} />
                <Route path="privacy" element={<LegalDoc doc="privacy" />} />
                <Route path="legal" element={<LegalDoc doc="legal" />} />
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
