import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from '@/components/Layout';
import Login from '@/pages/Login';
import DocumentForm from '@/pages/DocumentForm';
import DocumentList from '@/pages/DocumentList';
import DocumentDetail from '@/pages/DocumentDetail';
import { getToken } from '@/utils/storage';

// 受保护路由：检查 localStorage 中是否有 token，没有则重定向到登录页
function ProtectedRoute({ children }: { children: JSX.Element }) {
  const token = getToken();
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

// 路由配置：公开路由 + 受保护路由
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      {/* 受保护路由都套在 Layout 中 */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/documents" replace />} />
        <Route path="documents" element={<DocumentList />} />
        <Route path="documents/new" element={<DocumentForm />} />
        <Route path="documents/:id" element={<DocumentDetail />} />
      </Route>

      {/* 兜底：未匹配跳回列表 */}
      <Route path="*" element={<Navigate to="/documents" replace />} />
    </Routes>
  );
}
