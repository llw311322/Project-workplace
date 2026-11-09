import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { clearAuth, getUser, type UserInfo } from '@/utils/storage';
import { useEffect, useState } from 'react';

/**
 * B 端主布局：侧边菜单 + 顶部栏 + 内容区
 *  - 顶部显示当前用户 + 退出按钮
 *  - 侧边菜单根据角色隐藏入口（示例：审批人可以看见"待我审批"）
 */
export default function Layout() {
  const [user, setUser] = useState<UserInfo | null>(getUser());
  const navigate = useNavigate();

  useEffect(() => {
    setUser(getUser());
  }, []);

  const logout = () => {
    clearAuth();
    navigate('/login', { replace: true });
  };

  // 菜单配置
  const menus = [
    { to: '/documents', label: '单据管理', icon: '📋' },
    { to: '/documents/new', label: '新建单据', icon: '➕' },
  ];

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-50">
      {/* ===== 侧边栏 ===== */}
      <aside className="flex w-56 flex-col border-r border-slate-200 bg-white">
        {/* Logo */}
        <div className="flex h-14 items-center gap-2 border-b border-slate-200 px-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-indigo-600 text-sm font-bold text-white">
            A
          </div>
          <div className="text-base font-semibold text-slate-800">智能审批</div>
        </div>
        {/* 菜单 */}
        <nav className="flex-1 space-y-1 px-2 py-3">
          {menus.map((m) => (
            <NavLink
              key={m.to}
              to={m.to}
              end={m.to === '/documents'}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? 'bg-indigo-50 text-indigo-700 font-medium'
                    : 'text-slate-600 hover:bg-slate-100'
                }`
              }
            >
              <span>{m.icon}</span>
              <span>{m.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* ===== 主区域 ===== */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* 顶部栏 */}
        <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-6">
          <div className="text-sm text-slate-500">企业内部单据审批系统</div>
          <div className="flex items-center gap-3">
            {user && (
              <>
                <div className="flex items-center gap-2 text-sm text-slate-700">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-indigo-600">
                    {(user.displayName ?? user.username).slice(0, 1).toUpperCase()}
                  </div>
                  <span>{user.displayName ?? user.username}</span>
                  <span className="text-xs text-slate-400">
                    ({user.role === 'approver' ? '审批人' : '提交人'})
                  </span>
                </div>
                <button className="btn-ghost" onClick={logout}>
                  退出
                </button>
              </>
            )}
          </div>
        </header>

        {/* 内容区（子路由渲染在这里） */}
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
