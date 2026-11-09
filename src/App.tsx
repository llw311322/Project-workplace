import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/layout/AppLayout'
import LoginPage from '@/pages/LoginPage'
import AboutPage from '@/pages/AboutPage'
import NewClaimPage from '@/pages/NewClaimPage'
import ClaimListPage from '@/pages/ClaimListPage'
import ClaimDetailPage from '@/pages/ClaimDetailPage'
import WorkbenchPage from '@/pages/WorkbenchPage'
import KnowledgePage from '@/pages/KnowledgePage'
import { session } from '@/lib/auth'

/** 未登录跳登录页；已登录访问 /login 跳工作台 */
function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!session.isLoggedIn()) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      {/* 作品说明页对外公开，不需要登录 */}
      <Route path="/about" element={<AboutPage />} />
      <Route
        path="/login"
        element={session.isLoggedIn() ? <Navigate to="/claims" replace /> : <LoginPage />}
      />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<WorkbenchPage />} />
        <Route path="/claims" element={<ClaimListPage mode="mine" />} />
        <Route path="/claims/new" element={<NewClaimPage />} />
        <Route path="/claims/:id" element={<ClaimDetailPage />} />
        <Route path="/pending" element={<ClaimListPage mode="pending" />} />
        <Route path="/kb" element={<KnowledgePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
