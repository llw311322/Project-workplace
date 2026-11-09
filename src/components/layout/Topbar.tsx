import { useNavigate } from 'react-router-dom'
import { Bell, LogOut, Menu, Search } from 'lucide-react'
import { session } from '@/lib/auth'
import { cn } from '@/lib/utils'

export function Topbar({
  breadcrumb,
  className,
  onMenuClick,
}: {
  breadcrumb: string
  className?: string
  onMenuClick?: () => void
}) {
  const navigate = useNavigate()
  const user = session.getUser()

  return (
    <header
      className={cn(
        'flex h-16 shrink-0 items-center justify-between gap-3 border-b border-line bg-white px-3 sm:px-4',
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-2">
        <button
          type="button"
          onClick={onMenuClick}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-ink-2 transition-colors hover:bg-field lg:hidden"
          aria-label="打开菜单"
        >
          <Menu className="h-5 w-5" />
        </button>
        <span className="truncate text-sm text-muted">{breadcrumb}</span>
      </div>

      <div className="flex shrink-0 items-center gap-3 sm:gap-4">
        <div className="hidden h-[34px] w-[220px] items-center gap-2 rounded-lg bg-[#F3F4F6] px-2.5 md:flex">
          <Search className="h-4 w-4 text-faint" />
          <input
            className="w-full bg-transparent text-[13px] outline-none placeholder:text-faint"
            placeholder="搜索单据 / 知识库"
            onKeyDown={(e) => {
              if (e.key === 'Enter') navigate(`/claims?keyword=${encodeURIComponent((e.target as HTMLInputElement).value)}`)
            }}
          />
        </div>

        <div className="relative">
          <Bell className="h-5 w-5 text-muted" strokeWidth={2} />
          <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-[#EF4444]" />
        </div>

        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs font-medium text-white">
            {(user?.name || '未').slice(0, 1)}
          </span>
          <span className="hidden text-[13px] font-medium text-ink sm:inline">{user?.name || '未登录'}</span>
          <span className="hidden rounded-md bg-primary-light px-1.5 py-0.5 text-[11px] font-medium text-primary sm:inline">
            {user?.role === 'approver' ? '审批人' : '提交人'}
          </span>
        </div>

        <button
          type="button"
          title="退出登录"
          onClick={() => {
            session.clear()
            navigate('/login', { replace: true })
          }}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-muted transition-colors hover:bg-field hover:text-ink-2"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </div>
    </header>
  )
}
