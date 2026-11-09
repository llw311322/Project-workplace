import { Link, useLocation } from 'react-router-dom'
import { Coffee, FilePlus2, FileText, Home, BookOpen, ClipboardCheck, Info } from 'lucide-react'
import { cn } from '@/lib/utils'
import { session } from '@/lib/auth'

export type NavKey = 'home' | 'submit' | 'claims' | 'pending' | 'kb'

const NAV_ITEMS: { key: NavKey; label: string; to: string; icon: typeof Home }[] = [
  { key: 'home', label: '工作台', to: '/', icon: Home },
  { key: 'submit', label: '单据提交', to: '/claims/new', icon: FilePlus2 },
  { key: 'claims', label: '我的单据', to: '/claims', icon: FileText },
  { key: 'pending', label: '待我审批', to: '/pending', icon: ClipboardCheck },
  { key: 'kb', label: '制度知识库', to: '/kb', icon: BookOpen },
]

export function Sidebar({
  pendingCount = 0,
  onNavigate,
}: {
  pendingCount?: number
  onNavigate?: () => void
}) {
  const { pathname } = useLocation()
  const user = session.getUser()

  return (
    <aside className="flex h-full w-60 shrink-0 flex-col bg-navy shadow-2xl lg:shadow-none">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-4">
        <span className="flex h-[26px] w-[26px] items-center justify-center rounded-md bg-white/10">
          <Coffee className="h-[18px] w-[18px] text-white" strokeWidth={2} />
        </span>
        <span className="text-[17px] font-bold text-white">魔饮咖啡</span>
        <span className="ml-auto rounded-full bg-navy-soft px-2 py-1 text-[10px] leading-none text-primary-soft">
          内部工作台
        </span>
      </div>

      {/* 导航 */}
      <nav className="flex flex-col gap-1 px-2 py-2">
        {NAV_ITEMS.map((item) => {
          const active =
            item.key === 'home' ? pathname === '/' : pathname === item.to || pathname.startsWith(`${item.to}/`)
          const Icon = item.icon
          return (
            <Link
              key={item.key}
              to={item.to}
              onClick={onNavigate}
              className={cn(
                'relative flex h-10 items-center gap-2.5 rounded-lg px-2.5 text-sm transition-colors',
                active ? 'bg-navy-soft font-medium text-white' : 'text-navy-text hover:bg-white/5',
              )}
            >
              {active && (
                <span className="absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r-full bg-primary" />
              )}
              <Icon className={cn('h-[18px] w-[18px]', active ? 'text-white' : 'text-[#9CA3AF]')} strokeWidth={2} />
              {item.label}
              {item.key === 'pending' && pendingCount > 0 && (
                <span className="ml-auto flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-primary px-1 text-[10px] font-medium text-white">
                  {pendingCount > 99 ? '99+' : pendingCount}
                </span>
              )}
            </Link>
          )
        })}
      </nav>

      <div className="mx-4 h-px bg-navy-soft" />

      {/* 作品说明入口：面试官可从系统内回到项目介绍 */}
      <div className="px-2 py-2">
        <Link
          to="/about"
          onClick={onNavigate}
          className="flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-[13px] text-navy-text transition-colors hover:bg-white/5"
        >
          <Info className="h-[17px] w-[17px] text-[#9CA3AF]" strokeWidth={2} />
          关于本项目
        </Link>
      </div>

      {/* 底部用户信息 */}
      <div className="mt-auto flex items-center gap-2.5 px-4 py-3.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-xs font-medium text-white">
          {(user?.name || '未').slice(0, 1)}
        </span>
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-white">{user?.name || '未登录'}</p>
          <p className="truncate text-[11px] text-navy-muted">
            {user?.role === 'approver' ? '审批人' : '员工'} ·{' '}
            {user?.workshop || (user?.account ? `工号 ${user.account}` : '—')}
          </p>
        </div>
      </div>
    </aside>
  )
}
