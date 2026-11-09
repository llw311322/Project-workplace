import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'
import { claimApi } from '@/lib/api'
const BREADCRUMB_MAP: [RegExp, string][] = [
  [/^\/$/, '工作台 / 首页'],
  [/^\/claims\/new/, '工作台 / 单据提交 / 新建申领单'],
  [/^\/claims\/[^/]+$/, '工作台 / 我的单据 / 单据详情'],
  [/^\/claims/, '工作台 / 我的单据'],
  [/^\/pending/, '工作台 / 待我审批'],
  [/^\/kb/, '工作台 / 制度知识库'],
]

function breadcrumbFor(pathname: string) {
  return BREADCRUMB_MAP.find(([re]) => re.test(pathname))?.[1] ?? '工作台'
}

export function AppLayout() {
  const { pathname } = useLocation()
  const [pendingCount, setPendingCount] = useState(0)
  // 窄屏（<lg）侧边栏改为抽屉，默认收起
  const [menuOpen, setMenuOpen] = useState(false)

  // 侧边栏「待我审批」角标
  useEffect(() => {
    claimApi
      .listPending({ page: 1, pageSize: 1 })
      .then((res) => setPendingCount(res.total))
      .catch(() => setPendingCount(0))
  }, [pathname])

  // 切换页面自动收起抽屉，避免点完导航还挡着内容
  useEffect(() => {
    setMenuOpen(false)
  }, [pathname])

  return (
    <div className="flex h-screen w-full overflow-hidden bg-page text-ink">
      {/* 抽屉遮罩 */}
      {menuOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/40 lg:hidden"
          onClick={() => setMenuOpen(false)}
          aria-hidden
        />
      )}

      <div
        className={`fixed inset-y-0 left-0 z-40 transition-transform duration-200 lg:static lg:translate-x-0 ${
          menuOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <Sidebar pendingCount={pendingCount} onNavigate={() => setMenuOpen(false)} />
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar breadcrumb={breadcrumbFor(pathname)} onMenuClick={() => setMenuOpen(true)} />
        <main className="min-h-0 flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
