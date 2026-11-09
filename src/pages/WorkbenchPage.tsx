import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, BookOpen, ClipboardCheck, FilePlus2, FileText, Sparkles } from 'lucide-react'
import { claimApi } from '@/lib/api'
import { session } from '@/lib/auth'
import { Card } from '@/components/ui/card'
import { StatusBadge } from '@/components/ui/status-badge'
import type { Claim } from '@/lib/types'
import { formatShort } from '@/lib/utils'

export default function WorkbenchPage() {
  const user = session.getUser()
  const [recent, setRecent] = useState<Claim[]>([])
  const [stats, setStats] = useState({ total: 0, pending: 0, approved: 0, rejected: 0 })

  useEffect(() => {
    claimApi
      .listMine({ page: 1, pageSize: 50 })
      .then((res) => {
        setRecent(res.list.slice(0, 6))
        setStats({
          total: res.total,
          pending: res.list.filter((c) => c.status === 'submitted' || c.status === 'approving').length,
          approved: res.list.filter((c) => c.status === 'approved').length,
          rejected: res.list.filter((c) => c.status === 'rejected').length,
        })
      })
      .catch(() => undefined)
  }, [])

  const cards = [
    { label: '累计单据', value: stats.total, to: '/claims', icon: FileText },
    { label: '进行中审批', value: stats.pending, to: '/claims', icon: ClipboardCheck },
    { label: '审批通过', value: stats.approved, to: '/claims', icon: FileText },
    { label: '已驳回', value: stats.rejected, to: '/claims', icon: FileText },
  ]

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-[960px] flex-col gap-4 p-4 md:p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl font-bold text-ink">
              你好，{user?.name || '同事'}
            </h1>
            <p className="mt-1 text-[13px] text-muted">欢迎回到魔饮咖啡内部业务工作台</p>
          </div>
          <Link
            to="/claims/new"
            className="inline-flex h-10 items-center justify-center gap-1.5 rounded-lg bg-primary px-4 text-sm font-medium text-white hover:bg-primary-hover"
          >
            <FilePlus2 className="h-4 w-4" /> 新建申领单
          </Link>
        </div>

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {cards.map((c) => (
            <Link key={c.label} to={c.to}>
              <Card className="p-4 transition-colors hover:border-primary/40">
                <p className="text-[13px] text-muted">{c.label}</p>
                <p className="mt-1 text-2xl font-bold text-ink">{c.value}</p>
              </Card>
            </Link>
          ))}
        </div>

        {/* 知识库入口：首页可达，避免第一次进来找不到 */}
        <Link to="/kb" className="group">
          <Card className="flex items-center gap-3 border-line p-4 transition-colors group-hover:border-primary/40">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-light">
              <BookOpen className="h-5 w-5 text-primary" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-ink">制度知识库</p>
              <p className="mt-0.5 text-[12px] leading-5 text-muted">
                32 份制度、条款级检索，答案能指到「第 4.2 条」，并按密级自动过滤
              </p>
            </div>
            <ArrowRight className="h-4 w-4 shrink-0 text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
          </Card>
        </Link>

        <Card className="flex flex-col gap-2 p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-[15px] font-semibold text-ink">最近单据</h2>
            <Link to="/claims" className="flex items-center gap-1 text-[13px] text-primary hover:underline">
              查看全部 <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
          {recent.length === 0 && <p className="py-6 text-center text-[13px] text-faint">暂无单据</p>}
          <div className="flex flex-col">
            {recent.map((claim) => (
              <Link
                key={claim.id}
                to={`/claims/${claim.id}`}
                className="flex items-center justify-between border-b border-line-soft py-3 last:border-0 hover:bg-[#F7F8FA]"
              >
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-medium text-ink">{claim.title}</p>
                  <p className="text-xs text-faint">
                    {claim.code} · {formatShort(claim.submittedAt)}
                  </p>
                </div>
                <StatusBadge status={claim.status} />
              </Link>
            ))}
          </div>
        </Card>

        <Card className="flex items-start gap-3 border-primary/30 bg-primary-light p-4">
          <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
          <div>
            <p className="text-sm font-medium text-primary-deep">AI 助手已就绪</p>
            <p className="mt-1 text-[13px] leading-6 text-primary-ink">
              打开任意单据详情即可在右侧与 AI 助手对话：生成摘要、校验合规、查询库存、生成审批备注。LLM 异常时自动降级，不影响单据保存与审批。
            </p>
          </div>
        </Card>
      </div>
    </div>
  )
}
