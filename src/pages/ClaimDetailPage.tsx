import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2, Loader2, Sparkles } from 'lucide-react'
import { claimApi } from '@/lib/api'
import { session } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Card, CardTitle } from '@/components/ui/card'
import { StatusBadge } from '@/components/ui/status-badge'
import { AgentPanel } from '@/components/AgentPanel'
import { RejectDialog } from '@/components/RejectDialog'
import type { ApprovalRecord, Claim } from '@/lib/types'
import { cn, formatDateTime, formatShort } from '@/lib/utils'

/** 状态流转条：草稿 → 已提交 → 审批中 → 审批通过（驳回则单独标红） */
function StatusFlow({ claim }: { claim: Claim }) {
  const steps: { label: string; sub: string; state: 'done' | 'current' | 'todo' | 'reject' }[] = [
    { label: '草稿', sub: formatShort(claim.createdAt), state: 'done' },
    {
      label: '已提交',
      sub: formatShort(claim.submittedAt),
      state: claim.status === 'draft' ? 'todo' : 'done',
    },
    {
      label: '审批中',
      sub: claim.approver ? `审批人：${claim.approver}` : '—',
      state:
        claim.status === 'draft' || claim.status === 'submitted'
          ? claim.status === 'submitted'
            ? 'current'
            : 'todo'
          : claim.status === 'approving'
            ? 'current'
            : 'done',
    },
    {
      label: claim.status === 'rejected' ? '已驳回' : '审批通过',
      sub: claim.status === 'draft' ? '未开始' : claim.status === 'rejected' ? '请修改后重新提交' : claim.status === 'approved' ? '已完成' : '待审批',
      state: claim.status === 'rejected' ? 'reject' : claim.status === 'approved' ? 'done' : 'todo',
    },
  ]

  const circleCls = (state: string) =>
    state === 'done'
      ? 'border-[#22C55E] bg-[#22C55E] text-white'
      : state === 'current'
        ? 'border-primary bg-primary-light'
        : state === 'reject'
          ? 'border-[#EF4444] bg-[#FEE2E2]'
          : 'border-[#D1D5DB] bg-white'

  return (
    <Card className="flex items-center gap-1.5 px-3 py-3.5 sm:gap-2 sm:px-[18px] sm:py-[18px]">
      {steps.map((step, i) => (
        <div key={step.label} className={cn('flex items-center gap-1.5 sm:gap-2', i < steps.length - 1 && 'flex-1')}>
          <div className="flex items-center gap-1.5 sm:gap-2">
            <span
              className={cn(
                'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 sm:h-6 sm:w-6',
                circleCls(step.state),
              )}
            >
              {step.state === 'done' && <CheckCircle2 className="h-3 w-3 sm:h-4 sm:w-4" />}
              {step.state === 'current' && <span className="h-2 w-2 rounded-full bg-primary" />}
              {step.state === 'reject' && <span className="h-2 w-2 rounded-full bg-[#EF4444]" />}
            </span>
            <div className="leading-tight">
              <p
                className={cn(
                  'whitespace-nowrap text-[12px] font-medium sm:text-[13px]',
                  step.state === 'todo' ? 'text-faint' : step.state === 'reject' ? 'text-[#B91C1C]' : step.state === 'current' ? 'text-primary' : 'text-ink',
                )}
              >
                {step.label}
              </p>
              <p className="hidden text-[11px] text-faint sm:block">{step.sub}</p>
            </div>
          </div>
          {i < steps.length - 1 && (
            <div
              className={cn(
                'h-0.5 min-w-2 flex-1 rounded-full sm:min-w-6',
                steps[i].state === 'done' ? 'bg-[#22C55E]' : 'bg-[#E5E7EB]',
              )}
            />
          )}
        </div>
      ))}
    </Card>
  )
}

const ACTION_LABEL: Record<string, string> = {
  create: '创建单据',
  submit: '提交单据',
  withdraw: '撤销提交',
  approve: '同意',
  reject: '驳回',
  ai_validate: '系统 AI 辅助校验',
}

export default function ClaimDetailPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const user = session.getUser()

  const [claim, setClaim] = useState<Claim | null>(null)
  const [history, setHistory] = useState<ApprovalRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [acting, setActing] = useState<'withdraw' | 'approve' | 'reject' | null>(null)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)

  const notify = useCallback((type: 'ok' | 'err', text: string) => {
    setToast({ type, text })
    window.setTimeout(() => setToast(null), 2600)
  }, [])

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([claimApi.detail(id), claimApi.history(id)])
      .then(([c, h]) => {
        setClaim(c)
        setHistory(h)
      })
      .catch((err) => setError(err instanceof Error ? err.message : '单据加载失败'))
      .finally(() => setLoading(false))
  }, [id])

  useEffect(load, [load])

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-muted">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> 加载单据中…
      </div>
    )
  }
  if (error || !claim) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-muted">
        <p>{error || '单据不存在'}</p>
        <Button variant="secondary" onClick={() => navigate('/claims')}>
          返回我的单据
        </Button>
      </div>
    )
  }

  const canWithdraw = claim.status === 'submitted' || claim.status === 'approving'
  const canReview = canWithdraw && user?.role === 'approver'

  const doWithdraw = async () => {
    setActing('withdraw')
    try {
      await claimApi.withdraw(claim.id)
      notify('ok', '已撤销提交，单据回到草稿状态')
      load()
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '操作失败')
    } finally {
      setActing(null)
    }
  }

  const doApprove = async () => {
    setActing('approve')
    try {
      await claimApi.approve(claim.id, '同意，请按期配送')
      notify('ok', '审批通过')
      load()
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '操作失败')
    } finally {
      setActing(null)
    }
  }

  const doReject = async (comment: string) => {
    setActing('reject')
    try {
      await claimApi.reject(claim.id, comment)
      setRejectOpen(false)
      notify('ok', '已驳回，单据退回提交人修改')
      load()
    } finally {
      setActing(null)
    }
  }

  return (
    <div className="flex h-full flex-col lg:flex-row">
      {/* 左侧内容 */}
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-[760px] flex-col gap-4 p-4 md:p-6">
          {/* 头部 */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex flex-col gap-1.5">
              <Link to="/claims" className="text-xs text-primary hover:underline">
                ← 返回我的单据
              </Link>
              <div className="flex flex-wrap items-center gap-2.5">
                <h1 className="text-lg font-bold text-ink">
                  {claim.code} · {claim.title}
                </h1>
                <StatusBadge status={claim.status} />
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2.5">
              {canWithdraw && (
                <Button variant="secondary" onClick={doWithdraw} disabled={acting !== null}>
                  {acting === 'withdraw' ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  撤销提交
                </Button>
              )}
              {canReview && (
                <>
                  <Button variant="danger" onClick={() => setRejectOpen(true)} disabled={acting !== null}>
                    驳回
                  </Button>
                  <Button onClick={doApprove} disabled={acting !== null}>
                    {acting === 'approve' ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                    同意
                  </Button>
                </>
              )}
            </div>
          </div>

          <StatusFlow claim={claim} />

          {/* 单据信息 */}
          <Card className="flex flex-col gap-3.5 p-[18px]">
            <CardTitle>单据信息</CardTitle>
            <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-3">
              {[
                { label: '申领人', value: `${claim.applicant}（${claim.applicantTitle}）` },
                { label: '申领车间', value: `${claim.workshop}（${claim.workshopCode}）` },
                { label: '联系电话', value: claim.phone },
                { label: '需求日期', value: claim.demandDate },
                { label: '紧急程度', value: claim.urgency === 'urgent' ? '加急' : '普通' },
                { label: '提交时间', value: formatDateTime(claim.submittedAt) },
              ].map((f) => (
                <div key={f.label} className="flex flex-col gap-1">
                  <p className="text-xs text-faint">{f.label}</p>
                  <p className="text-sm font-medium text-ink">{f.value || '—'}</p>
                </div>
              ))}
            </div>
            {claim.remark && (
              <div className="rounded-lg bg-field p-3 text-[13px] leading-6 text-ink-3">{claim.remark}</div>
            )}
          </Card>

          {/* 货品明细 */}
          <Card className="flex flex-col gap-3 p-[18px]">
            <CardTitle>货品明细（{claim.items.length} 项）</CardTitle>
            <div className="overflow-x-auto rounded-lg border border-line">
              <table className="w-full min-w-[520px] text-left text-[13px]">
                <thead>
                  <tr className="h-9 bg-[#F7F8FA] text-xs font-medium text-muted">
                    <th className="px-3 font-medium">货品名称</th>
                    <th className="w-[150px] px-3 font-medium">规格</th>
                    <th className="w-[90px] px-3 font-medium">数量</th>
                    <th className="px-3 font-medium">用途备注</th>
                  </tr>
                </thead>
                <tbody>
                  {claim.items.map((item) => (
                    <tr key={item.id} className="border-t border-line-soft">
                      <td className="px-3 py-2.5 text-ink">{item.name}</td>
                      <td className="px-3 py-2.5 text-ink-3">{item.spec}</td>
                      <td className="px-3 py-2.5 font-medium text-ink">
                        {item.quantity} {item.unit}
                      </td>
                      <td className="px-3 py-2.5 text-ink-3">{item.purpose}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* 审批历史 */}
          <Card className="flex flex-col gap-3.5 p-[18px]">
            <CardTitle>审批历史（留痕记录）</CardTitle>
            {history.length === 0 && <p className="text-[13px] text-faint">暂无记录，提交后开始留痕</p>}
            <div className="flex flex-col">
              {history.map((rec, idx) => (
                <div key={rec.id} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <span
                      className={cn(
                        'mt-1 h-2.5 w-2.5 rounded-full',
                        rec.action === 'approve'
                          ? 'bg-[#22C55E]'
                          : rec.action === 'reject'
                            ? 'bg-[#EF4444]'
                            : rec.action === 'withdraw'
                              ? 'bg-[#9CA3AF]'
                              : 'bg-primary',
                      )}
                    />
                    {idx < history.length - 1 && <span className="w-px flex-1 bg-[#E5E7EB]" />}
                  </div>
                  <div className="flex-1 pb-4">
                    <div className="flex items-center justify-between gap-2">
                      <p className="flex items-center gap-2 text-[13px] font-medium text-ink">
                        {rec.operator} {ACTION_LABEL[rec.action] ?? rec.action}
                        {rec.fromAgent && (
                          <span className="inline-flex items-center gap-1 rounded-md bg-primary-light px-1.5 py-0.5 text-[10px] font-medium text-primary">
                            <Sparkles className="h-3 w-3" /> Agent 插件
                          </span>
                        )}
                      </p>
                      <p className="shrink-0 text-xs text-faint">{formatDateTime(rec.createdAt)}</p>
                    </div>
                    {rec.comment && <p className="mt-1 text-xs leading-5 text-muted">{rec.comment}</p>}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      {/* 右侧 Agent 面板 */}
      <AgentPanel claim={claim} />

      <RejectDialog
        open={rejectOpen}
        loading={acting === 'reject'}
        onCancel={() => setRejectOpen(false)}
        onConfirm={doReject}
      />

      {toast && (
        <div
          className={`fixed left-1/2 top-6 z-50 -translate-x-1/2 rounded-lg px-4 py-2.5 text-sm text-white shadow-lg ${
            toast.type === 'ok' ? 'bg-[#15803D]' : 'bg-[#B91C1C]'
          }`}
        >
          {toast.text}
        </div>
      )}
    </div>
  )
}
