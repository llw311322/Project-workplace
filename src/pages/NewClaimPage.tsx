import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { CheckCircle2, Loader2, Plus, ShieldCheck, Sparkles, Trash2, TriangleAlert } from 'lucide-react'
import { agentApi, claimApi } from '@/lib/api'
import { session } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Input, Label, Select, Textarea } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { ClaimItem, ClaimSummary, ClaimValidation, Claim, Urgency } from '@/lib/types'
import { formatDate } from '@/lib/utils'

const WORKSHOPS = [
  '萃取车间（EX-01）',
  '冻干车间（FZ-02）',
  '包装车间（BZ-01）',
  '研发中试车间（YF-01）',
  '仓储部（WH-01）',
]

const emptyItem = (): ClaimItem => ({
  id: `i-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
  name: '',
  spec: '',
  quantity: 1,
  unit: '件',
  purpose: '',
})

export default function NewClaimPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const user = session.getUser()

  // 已存在单据（草稿 / 驳回后重新编辑）时加载
  const [claimId, setClaimId] = useState<string | null>(params.get('id'))
  const [claimCode, setClaimCode] = useState<string>('')

  const [title, setTitle] = useState('')
  const [workshop, setWorkshop] = useState(WORKSHOPS[0])
  const [applicant, setApplicant] = useState(`${user?.name || ''}（${user?.title || '员工'}）`)
  const [phone, setPhone] = useState('')
  const [demandDate, setDemandDate] = useState('')
  const [urgency, setUrgency] = useState<Urgency>('normal')
  const [remark, setRemark] = useState('')
  const [items, setItems] = useState<ClaimItem[]>([emptyItem(), emptyItem()])

  const [summary, setSummary] = useState<ClaimSummary | null>(null)
  const [validation, setValidation] = useState<ClaimValidation | null>(null)
  const [aiLoading, setAiLoading] = useState<'summary' | 'validate' | null>(null)
  const [saving, setSaving] = useState<'draft' | 'submit' | null>(null)
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)

  const notify = useCallback((type: 'ok' | 'err', text: string) => {
    setToast({ type, text })
    window.setTimeout(() => setToast(null), 2600)
  }, [])

  useEffect(() => {
    if (!claimId) return
    claimApi
      .detail(claimId)
      .then((c: Claim) => {
        setClaimCode(c.code)
        setTitle(c.title)
        setWorkshop(`${c.workshop}（${c.workshopCode}）`)
        setApplicant(`${c.applicant}（${c.applicantTitle}）`)
        setPhone(c.phone)
        setDemandDate(c.demandDate)
        setUrgency(c.urgency)
        setRemark(c.remark)
        setItems(c.items.length ? c.items : [emptyItem()])
      })
      .catch(() => notify('err', '单据加载失败'))
  }, [claimId, notify])

  const payload = useMemo(
    () => ({
      title,
      workshop: workshop.split('（')[0] || workshop,
      workshopCode: (workshop.match(/（(.+)）/) ?? [])[1] ?? '',
      applicant: applicant.split('（')[0] || applicant,
      applicantTitle: (applicant.match(/（(.+)）/) ?? [])[1] ?? '',
      phone,
      demandDate,
      urgency,
      remark,
      items: items.filter((i) => i.name.trim()),
    }),
    [title, workshop, applicant, phone, demandDate, urgency, remark, items],
  )

  /* ------------------------------------------------------------ 单据操作 */

  const ensureDraft = async (): Promise<string | null> => {
    if (claimId) return claimId
    const created = await claimApi.create(payload)
    setClaimId(created.id)
    setClaimCode(created.code)
    return created.id
  }

  const handleSaveDraft = async () => {
    if (!title.trim()) return notify('err', '请至少填写单据标题')
    setSaving('draft')
    try {
      const id = await ensureDraft()
      await claimApi.saveDraft(id!, payload)
      notify('ok', '草稿已保存，可随时继续编辑')
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(null)
    }
  }

  const handleSubmit = async () => {
    if (!title.trim()) return notify('err', '请填写单据标题')
    if (!demandDate) return notify('err', '请选择需求日期')
    if (!payload.items.length) return notify('err', '请至少添加一条货品明细')
    setSaving('submit')
    try {
      const id = await ensureDraft()
      await claimApi.saveDraft(id!, payload)
      await claimApi.submit(id!)
      navigate(`/claims/${id}`, { replace: true })
    } catch (err) {
      notify('err', err instanceof Error ? err.message : '提交失败')
    } finally {
      setSaving(null)
    }
  }

  /* ------------------------------------------------------------ AI 能力 */

  const handleSummary = async () => {
    setAiLoading('summary')
    setSummary(await agentApi.summary(payload))
    setAiLoading(null)
  }

  const handleValidate = async () => {
    setAiLoading('validate')
    setValidation(await agentApi.validate(payload))
    setAiLoading(null)
  }

  /* ------------------------------------------------------------ 明细行 */

  const updateItem = (id: string, patch: Partial<ClaimItem>) =>
    setItems((list) => list.map((i) => (i.id === id ? { ...i, ...patch } : i)))

  const removeItem = (id: string) =>
    setItems((list) => (list.length > 1 ? list.filter((i) => i.id !== id) : [emptyItem()]))

  const aiCard = summary || validation

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-[960px] flex-col gap-4 p-4 md:p-6">
        {/* 标题 + AI 按钮 */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-ink">新建货品申领单</h1>
            <p className="mt-1 text-[13px] text-muted">
              {claimCode ? `当前单据：${claimCode} · ` : ''}草稿自动保存 · 提交后进入审批流程，每一步操作留痕
            </p>
          </div>
          <div className="flex gap-2.5">
            <Button variant="soft" onClick={handleSummary} disabled={aiLoading !== null}>
              {aiLoading === 'summary' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              AI 一键摘要
            </Button>
            <Button variant="soft" onClick={handleValidate} disabled={aiLoading !== null}>
              {aiLoading === 'validate' ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              AI 校验
            </Button>
          </div>
        </div>

        {/* 表单卡片 */}
        <Card className="flex flex-col gap-4 p-4 md:p-6">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label required>单据标题</Label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="如：11月出口订单备料（冷萃咖啡液产线）" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label required>申领车间</Label>
              <Select value={workshop} onChange={(e) => setWorkshop(e.target.value)} className="h-[42px]">
                {WORKSHOPS.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>申领人</Label>
              <Input value={applicant} onChange={(e) => setApplicant(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>联系电话</Label>
              <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="138****6688" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label required>需求日期</Label>
              <Input type="date" value={demandDate} min={formatDate(new Date().toISOString())} onChange={(e) => setDemandDate(e.target.value)} className="h-[42px]" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>紧急程度</Label>
              <div className="flex gap-2.5">
                {(
                  [
                    { key: 'normal', label: '普通' },
                    { key: 'urgent', label: '加急' },
                  ] as const
                ).map((opt) => (
                  <button
                    key={opt.key}
                    type="button"
                    onClick={() => setUrgency(opt.key)}
                    className={`flex h-[42px] flex-1 items-center justify-center gap-1.5 rounded-lg text-sm transition-colors ${
                      urgency === opt.key
                        ? 'border-[1.5px] border-primary bg-primary-light font-medium text-primary'
                        : 'border border-field-border bg-white text-muted hover:border-faint'
                    }`}
                  >
                    <span className={`h-3.5 w-3.5 rounded-full ${urgency === opt.key ? 'border-4 border-primary' : 'border-2 border-[#D1D5DB]'}`} />
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="h-px bg-[#EEF0F3]" />

          {/* 货品明细 */}
          <div className="flex items-center justify-between">
            <h2 className="text-[15px] font-semibold text-ink">货品明细</h2>
            <Button variant="secondary" size="sm" className="h-8 border-primary text-primary hover:bg-primary-light" onClick={() => setItems((l) => [...l, emptyItem()])}>
              <Plus className="h-3.5 w-3.5" /> 添加明细行
            </Button>
          </div>

          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full min-w-[560px] text-left text-[13px]">
              <thead>
                <tr className="h-10 bg-[#F7F8FA] text-xs font-medium text-muted">
                  <th className="px-3 font-medium">货品名称</th>
                  <th className="w-[150px] px-3 font-medium">规格</th>
                  <th className="w-[110px] px-3 font-medium">申领数量</th>
                  <th className="px-3 font-medium">用途备注</th>
                  <th className="w-16 px-3 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-t border-line-soft">
                    <td className="px-2 py-1.5">
                      <input
                        className="w-full rounded-md border border-transparent bg-transparent px-1.5 py-1.5 outline-none hover:border-field-border focus:border-primary focus:bg-white"
                        value={item.name}
                        onChange={(e) => updateItem(item.id, { name: e.target.value })}
                        placeholder="如：埃塞俄比亚水洗生咖啡豆 G1"
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <input
                        className="w-full rounded-md border border-transparent bg-transparent px-1.5 py-1.5 outline-none hover:border-field-border focus:border-primary focus:bg-white"
                        value={item.spec}
                        onChange={(e) => updateItem(item.id, { spec: e.target.value })}
                        placeholder="60kg / 袋"
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <div className="flex items-center gap-1">
                        <input
                          type="number"
                          min={1}
                          className="w-16 rounded-md border border-transparent bg-transparent px-1.5 py-1.5 text-right font-medium outline-none hover:border-field-border focus:border-primary focus:bg-white"
                          value={item.quantity}
                          onChange={(e) => updateItem(item.id, { quantity: Number(e.target.value) || 0 })}
                        />
                        <input
                          className="w-14 rounded-md border border-transparent bg-transparent px-1.5 py-1.5 outline-none hover:border-field-border focus:border-primary focus:bg-white"
                          value={item.unit}
                          onChange={(e) => updateItem(item.id, { unit: e.target.value })}
                          placeholder="单位"
                        />
                      </div>
                    </td>
                    <td className="px-2 py-1.5">
                      <input
                        className="w-full rounded-md border border-transparent bg-transparent px-1.5 py-1.5 outline-none hover:border-field-border focus:border-primary focus:bg-white"
                        value={item.purpose}
                        onChange={(e) => updateItem(item.id, { purpose: e.target.value })}
                        placeholder="产线排产 / 出口订单备料"
                      />
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      <button
                        type="button"
                        onClick={() => removeItem(item.id)}
                        className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-[#EF4444] hover:bg-[#FEF2F2]"
                      >
                        <Trash2 className="h-3.5 w-3.5" /> 删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>备注说明</Label>
            <Textarea value={remark} onChange={(e) => setRemark(e.target.value)} placeholder="到厂时间要求、验收方式、关联订单等" />
          </div>
        </Card>

        {/* AI 反馈卡片 */}
        {aiCard && (
          <Card className="flex flex-col gap-2.5 border-primary/30 bg-primary-light p-4">
            <div className="flex items-center gap-2">
              <Sparkles className="h-[18px] w-[18px] text-primary" />
              <p className="text-sm font-medium text-primary-deep">{summary ? 'AI 摘要结果' : 'AI 校验结果'}</p>
              {validation && (
                <span
                  className={`ml-auto inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
                    validation.passed ? 'bg-[#DCFCE7] text-[#15803D]' : 'bg-[#FEF3C7] text-[#B45309]'
                  }`}
                >
                  {validation.passed ? <CheckCircle2 className="h-3.5 w-3.5" /> : <TriangleAlert className="h-3.5 w-3.5" />}
                  {validation.message}
                </span>
              )}
              {summary?.degraded && (
                <span className="ml-auto rounded-full bg-[#FEF3C7] px-2 py-0.5 text-xs font-medium text-[#B45309]">
                  已降级
                </span>
              )}
            </div>

            {summary && (
              <div className="flex items-start gap-2">
                <span className="shrink-0 rounded-md bg-primary px-2 py-0.5 text-[11px] font-medium text-white">AI 摘要</span>
                <p className="text-[13px] leading-[22px] text-primary-ink">{summary.summary}</p>
              </div>
            )}

            {validation && (validation.missingFields.length > 0 || validation.issues.length > 0) && (
              <ul className="list-inside list-disc text-[13px] leading-6 text-primary-ink">
                {validation.missingFields.map((f) => (
                  <li key={f}>缺少必填字段：{f}</li>
                ))}
                {validation.issues.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            )}
          </Card>
        )}

        {/* 底部操作栏 */}
        <Card className="sticky bottom-4 flex items-center justify-between gap-3 px-3.5 py-3.5 shadow-[0_8px_24px_rgba(10,13,58,0.08)]">
          <p className="hidden text-[13px] text-muted md:block">
            提交后将流转至生产经理审批 · 每一步操作将记入审批历史
          </p>
          <div className="flex gap-2.5">
            <Button variant="secondary" onClick={handleSaveDraft} disabled={saving !== null}>
              {saving === 'draft' ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              保存草稿
            </Button>
            <Button onClick={handleSubmit} disabled={saving !== null}>
              {saving === 'submit' ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              提交审批
            </Button>
          </div>
        </Card>
      </div>

      {/* 轻量 Toast */}
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
