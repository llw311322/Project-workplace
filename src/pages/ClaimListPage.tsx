import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Plus, RotateCcw, Search } from 'lucide-react'
import { claimApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input, Select } from '@/components/ui/input'
import { StatusBadge } from '@/components/ui/status-badge'
import type { Claim, ClaimListQuery, ClaimStatus, PageResult } from '@/lib/types'
import { formatShort } from '@/lib/utils'

const STATUS_OPTIONS: { value: ClaimStatus | 'all'; label: string }[] = [
  { value: 'all', label: '全部状态' },
  { value: 'draft', label: '草稿' },
  { value: 'submitted', label: '待审批' },
  { value: 'approving', label: '审批中' },
  { value: 'approved', label: '审批通过' },
  { value: 'rejected', label: '已驳回' },
]

const WORKSHOP_OPTIONS = ['全部车间', '萃取车间', '冻干车间', '包装车间', '研发中试车间', '仓储部']

/** 按状态给出对应操作入口（与设计稿一致） */
function rowActions(claim: Claim, mode: 'mine' | 'pending') {
  if (mode === 'pending') {
    return claim.status === 'submitted' || claim.status === 'approving' ? (
      <Link className="text-[13px] text-primary hover:underline" to={`/claims/${claim.id}`}>
        去审批
      </Link>
    ) : null
  }
  switch (claim.status) {
    case 'submitted':
    case 'approving':
      return <Link className="text-[13px] text-primary hover:underline" to={`/claims/${claim.id}`}>查看 · 撤销</Link>
    case 'rejected':
      return <Link className="text-[13px] text-primary hover:underline" to={`/claims/new?id=${claim.id}`}>查看 · 重新编辑</Link>
    case 'draft':
      return <Link className="text-[13px] text-primary hover:underline" to={`/claims/new?id=${claim.id}`}>编辑 · 提交</Link>
    default:
      return <Link className="text-[13px] text-primary hover:underline" to={`/claims/${claim.id}`}>查看</Link>
  }
}

export default function ClaimListPage({ mode = 'mine' }: { mode?: 'mine' | 'pending' }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState<Required<Pick<ClaimListQuery, 'status' | 'workshop' | 'keyword' | 'page' | 'pageSize'>> & { startDate: string; endDate: string }>({
    status: 'all',
    workshop: '全部车间',
    keyword: '',
    page: 1,
    pageSize: 10,
    startDate: '',
    endDate: '',
  })
  const [draft, setDraft] = useState(query.keyword)
  const [data, setData] = useState<PageResult<Claim> | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchList = useCallback(() => {
    setLoading(true)
    const req = mode === 'pending' ? claimApi.listPending : claimApi.listMine
    req(query)
      .then(setData)
      .catch(() => setData({ list: [], total: 0, page: 1, pageSize: query.pageSize }))
      .finally(() => setLoading(false))
  }, [mode, query])

  useEffect(fetchList, [fetchList])

  const totalPage = Math.max(1, Math.ceil((data?.total ?? 0) / query.pageSize))
  const isPending = mode === 'pending'

  return (
    <div className="h-full overflow-y-auto">
      <div className="flex flex-col gap-4 p-4 md:p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl font-bold text-ink">{isPending ? '待我审批' : '我的单据'}</h1>
            <p className="mt-1 text-[13px] text-muted">
              共 {data?.total ?? 0} 条记录 · 支持按状态、车间、时间筛选
            </p>
          </div>
          {!isPending && (
            <Button onClick={() => navigate('/claims/new')} className="justify-center">
              <Plus className="h-4 w-4" /> 新建申领单
            </Button>
          )}
        </div>

        {/* 筛选栏 */}
        <div className="flex flex-wrap items-center gap-3 rounded-card border border-line bg-white p-3.5">
          <Select
            value={query.status}
            onChange={(e) => setQuery((q) => ({ ...q, status: e.target.value as ClaimStatus | 'all', page: 1 }))}
            wrapperClassName="w-[calc(50%-6px)] sm:w-[130px]"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>

          <Select
            value={query.workshop}
            onChange={(e) => setQuery((q) => ({ ...q, workshop: e.target.value, page: 1 }))}
            wrapperClassName="w-[calc(50%-6px)] sm:w-[160px]"
          >
            {WORKSHOP_OPTIONS.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>

          <div className="flex w-full items-center gap-2 sm:w-auto">
            <Input
              type="date"
              value={query.startDate}
              onChange={(e) => setQuery((q) => ({ ...q, startDate: e.target.value, page: 1 }))}
              className="h-9 min-w-0 flex-1 bg-white sm:w-[140px] sm:flex-none"
            />
            <span className="text-xs text-faint">~</span>
            <Input
              type="date"
              value={query.endDate}
              onChange={(e) => setQuery((q) => ({ ...q, endDate: e.target.value, page: 1 }))}
              className="h-9 min-w-0 flex-1 bg-white sm:w-[140px] sm:flex-none"
            />
          </div>

          <div className="relative w-full min-w-0 sm:min-w-[200px] sm:flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
            <Input
              className="h-9 bg-white pl-9"
              placeholder="搜索单据编号 / 标题"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') setQuery((q) => ({ ...q, keyword: draft, page: 1 }))
              }}
              onBlur={() => setQuery((q) => (q.keyword === draft ? q : { ...q, keyword: draft, page: 1 }))}
            />
          </div>

          <Button
            variant="secondary"
            onClick={() => {
              setDraft('')
              setQuery({ status: 'all', workshop: '全部车间', keyword: '', page: 1, pageSize: 10, startDate: '', endDate: '' })
            }}
          >
            <RotateCcw className="h-3.5 w-3.5" /> 重置
          </Button>
        </div>

        {/* 移动端：卡片列表（6 列表格在窄屏不可读） */}
        <div className="flex flex-col gap-2.5 md:hidden">
          {loading && (
            <div className="rounded-card border border-line bg-white py-10 text-center text-[13px] text-muted">
              加载中…
            </div>
          )}
          {!loading && data?.list.length === 0 && (
            <div className="rounded-card border border-line bg-white py-10 text-center text-[13px] text-muted">
              暂无单据，点击「新建申领单」开始
            </div>
          )}
          {!loading &&
            data?.list.map((claim) => (
              <div key={claim.id} className="rounded-card border border-line bg-white p-3.5">
                <div className="flex items-start justify-between gap-2">
                  <Link to={`/claims/${claim.id}`} className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium text-ink">{claim.title}</p>
                    <p className="mt-1 text-xs text-faint">
                      {claim.code} · {claim.workshop}
                    </p>
                  </Link>
                  <StatusBadge status={claim.status} />
                </div>
                <div className="mt-2.5 flex items-center justify-between border-t border-line-soft pt-2.5">
                  <span className="text-xs text-faint">{formatShort(claim.submittedAt)}</span>
                  {rowActions(claim, mode)}
                </div>
              </div>
            ))}
        </div>

        {/* 桌面端：表格 */}
        <div className="hidden overflow-hidden rounded-card border border-line bg-white md:block">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="h-11 bg-[#F7F8FA] text-xs font-medium text-muted">
                <th className="w-[170px] px-4 font-medium">单据编号</th>
                <th className="px-4 font-medium">单据标题</th>
                <th className="w-[150px] px-4 font-medium">申领车间</th>
                <th className="w-[130px] px-4 font-medium">提交时间</th>
                <th className="w-[110px] px-4 font-medium">状态</th>
                <th className="w-[150px] px-4 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={6} className="h-24 text-center text-muted">
                    加载中…
                  </td>
                </tr>
              )}
              {!loading && data?.list.length === 0 && (
                <tr>
                  <td colSpan={6} className="h-24 text-center text-muted">
                    暂无单据，点击右上角「新建申领单」开始
                  </td>
                </tr>
              )}
              {!loading &&
                data?.list.map((claim) => (
                  <tr key={claim.id} className="border-t border-line-soft transition-colors hover:bg-[#F7F8FA]">
                    <td className="px-4 py-3.5">
                      <Link to={`/claims/${claim.id}`} className="font-medium text-primary hover:underline">
                        {claim.code}
                      </Link>
                    </td>
                    <td className="max-w-[280px] truncate px-4 py-3.5 text-ink" title={claim.title}>
                      {claim.title}
                    </td>
                    <td className="px-4 py-3.5 text-ink-3">{claim.workshop}</td>
                    <td className="px-4 py-3.5 text-ink-3">{formatShort(claim.submittedAt)}</td>
                    <td className="px-4 py-3.5">
                      <StatusBadge status={claim.status} />
                    </td>
                    <td className="px-4 py-3.5">{rowActions(claim, mode)}</td>
                  </tr>
                ))}
            </tbody>
          </table>

          {/* 分页 */}
          <div className="flex flex-col gap-2.5 border-t border-line-soft px-4 py-3 sm:h-14 sm:flex-row sm:items-center sm:justify-between sm:py-0">
            <p className="hidden text-[13px] text-muted sm:block">
              共 {data?.total ?? 0} 条记录 · 每页 {query.pageSize} 条
            </p>
            <div className="flex items-center justify-between gap-2 sm:justify-end">
              <Select
                value={String(query.pageSize)}
                onChange={(e) => setQuery((q) => ({ ...q, pageSize: Number(e.target.value), page: 1 }))}
                wrapperClassName="w-[96px]"
                className="h-8 text-xs"
              >
                <option value="10">10 条/页</option>
                <option value="20">20 条/页</option>
                <option value="50">50 条/页</option>
              </Select>
              <Button
                variant="secondary"
                className="h-8 w-8 p-0"
                disabled={query.page <= 1}
                onClick={() => setQuery((q) => ({ ...q, page: q.page - 1 }))}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="flex h-8 min-w-8 items-center justify-center rounded-lg bg-primary px-2 text-[13px] font-medium text-white">
                {query.page}
              </span>
              <span className="text-[13px] text-faint">/ {totalPage}</span>
              <Button
                variant="secondary"
                className="h-8 w-8 p-0"
                disabled={query.page >= totalPage}
                onClick={() => setQuery((q) => ({ ...q, page: q.page + 1 }))}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
