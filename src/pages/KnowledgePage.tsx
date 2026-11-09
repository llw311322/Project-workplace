import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertCircle,
  BookOpen,
  Clock,
  FileText,
  Layers,
  Lock,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react'
import { kbApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { MarkdownBody } from '@/components/KbDocViewer'
import { cn } from '@/lib/utils'
import type {
  Confidentiality,
  KbDoc,
  KbDocDetail,
  KbDocResult,
  KbSearchResult,
  KbStats,
} from '@/lib/types'

/** 密级标签：同一套配色，审批人和提交人看到的视觉语言一致 */
const CONF_STYLE: Record<Confidentiality, { label: string; cls: string }> = {
  public: { label: '公开', cls: 'bg-[#ECFDF5] text-[#047857]' },
  internal: { label: '内部', cls: 'bg-[#F3F4F6] text-[#4B5563]' },
  restricted: { label: '受限', cls: 'bg-[#FFF7ED] text-[#C2410C]' },
  secret: { label: '涉密', cls: 'bg-[#FEF2F2] text-[#B91C1C]' },
}

function ConfTag({ level }: { level: Confidentiality }) {
  const style = CONF_STYLE[level] ?? CONF_STYLE.internal
  return (
    <span className={cn('shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium leading-4', style.cls)}>
      {style.label}
    </span>
  )
}

/** 演示用的推荐问题：每条都对应一类真实审批场景 */
const SUGGESTIONS = [
  '驳回必须写意见吗',
  '加急单需要谁加签',
  '沙特出口标签有什么要求',
  '冻干产品塌陷怎么处置',
  'A 客户的配方能不能给 B 客户用',
]

export default function KnowledgePage() {
  const [stats, setStats] = useState<KbStats | null>(null)
  const [docs, setDocs] = useState<KbDocResult | null>(null)
  const [draft, setDraft] = useState('')
  const [result, setResult] = useState<KbSearchResult | null>(null)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState('')

  // 全文预览抽屉
  const [preview, setPreview] = useState<{
    docId: string
    loading: boolean
    data?: KbDocDetail
    error?: string
  } | null>(null)

  const openPreview = useCallback((docId: string) => {
    setPreview({ docId, loading: true })
    kbApi
      .docDetail(docId)
      .then((data) => setPreview({ docId, loading: false, data }))
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : '无法打开该制度'
        setPreview({ docId, loading: false, error: msg })
      })
  }, [])

  // Esc 关闭预览
  useEffect(() => {
    if (!preview) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPreview(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [preview])

  useEffect(() => {
    Promise.all([kbApi.stats(), kbApi.docs()])
      .then(([s, d]) => {
        setStats(s)
        setDocs(d)
        if (!s.available) setError(s.message || '知识库未加载')
      })
      .catch(() => setError('知识库接口不可用，请确认后端已启动'))
  }, [])

  const runSearch = useCallback((q: string) => {
    const query = q.trim()
    if (!query) return
    setDraft(query)
    setSearching(true)
    setError('')
    kbApi
      .search(query)
      .then(setResult)
      .catch(() => setError('检索失败，请稍后重试'))
      .finally(() => setSearching(false))
  }, [])

  // 制度目录按分类分组
  const grouped = useMemo(() => {
    const map = new Map<string, KbDoc[]>()
    for (const d of docs?.list ?? []) {
      const arr = map.get(d.category) ?? []
      arr.push(d)
      map.set(d.category, arr)
    }
    return Array.from(map.entries())
  }, [docs])

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
      {/* ------------------------------------------------ 左：检索与结果 */}
      <div className="min-w-0 flex-1 lg:overflow-y-auto">
        <div className="flex flex-col gap-4 p-4 md:p-6">
          <div>
            <h1 className="text-xl font-bold text-ink">制度知识库</h1>
            <p className="mt-1 text-[13px] text-muted">
              提问会定位到具体条款，并给出出处 · 结果已按「时效 / 密级 / 车间」三道门控过滤
            </p>
          </div>

          {/* 体检指标 */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              { icon: BookOpen, label: '制度份数', value: stats ? `${stats.total_loaded}` : '—', unit: '份' },
              { icon: Layers, label: '条款块', value: stats ? `${stats.chunks}` : '—', unit: '块' },
              {
                icon: ShieldCheck,
                label: '覆盖率',
                value: stats ? `${stats.coverage.toFixed(0)}` : '—',
                unit: '%',
              },
              {
                icon: FileText,
                label: '当前身份可见',
                value: stats ? `${stats.visible_docs}` : '—',
                unit: stats ? `/ ${stats.total_docs} 份` : '',
              },
            ].map((s) => (
              <div key={s.label} className="rounded-card border border-line bg-white px-4 py-3">
                <div className="flex items-center gap-1.5 text-xs text-muted">
                  <s.icon className="h-3.5 w-3.5" />
                  {s.label}
                </div>
                <p className="mt-1.5 text-[22px] font-bold leading-none text-ink">
                  {s.value}
                  <span className="ml-1 text-xs font-normal text-faint">{s.unit}</span>
                </p>
              </div>
            ))}
          </div>

          {/* 三道门控 */}
          {stats?.available && (
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-card border border-line bg-[#F7F8FA] px-4 py-2.5 text-xs text-ink-3">
              <span className="font-medium text-ink-2">检索门控</span>
              {stats.gates.map((g) => (
                <span key={g.key} className="flex items-center gap-1.5">
                  <span className="rounded bg-white px-1.5 py-0.5 font-medium text-primary">{g.key}</span>
                  {g.desc}
                </span>
              ))}
            </div>
          )}

          {/* 搜索 */}
          <div className="rounded-card border border-line bg-white p-4">
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
                <Input
                  className="h-11 pl-9"
                  placeholder="问一句业务问题，例如：驳回需要写意见吗"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') runSearch(draft)
                  }}
                />
              </div>
              <Button className="h-11 px-5" disabled={searching || !draft.trim()} onClick={() => runSearch(draft)}>
                {searching ? '检索中…' : '检索'}
              </Button>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-xs text-faint">常问：</span>
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => runSearch(s)}
                  className="rounded-full border border-line-soft bg-[#F7F8FA] px-2.5 py-1 text-xs text-ink-3 transition-colors hover:border-primary/40 hover:text-primary"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div className="flex items-center gap-2 rounded-card border border-[#FECACA] bg-[#FEF2F2] px-4 py-3 text-[13px] text-[#B91C1C]">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          )}

          {/* 结果 */}
          {result && (
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[13px] text-muted">
                  命中 <span className="font-medium text-ink">{result.total}</span> 条条款 · 耗时{' '}
                  <span className="font-medium text-ink">{result.elapsed_ms}</span> ms
                </p>
                <p className="flex items-center gap-1.5 text-xs text-faint">
                  <Clock className="h-3.5 w-3.5" />
                  仅检索已生效版本
                </p>
              </div>

              {result.suppressed_docs > 0 && (
                <div className="flex items-start gap-2 rounded-card border border-[#FDE68A] bg-[#FFFBEB] px-4 py-2.5 text-[13px] text-[#92400E]">
                  <Lock className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>
                    另有 <span className="font-semibold">{result.suppressed_docs}</span>{' '}
                    份制度因密级（受限 / 涉密）不对当前身份开放，已从结果中剔除
                  </span>
                </div>
              )}

              {result.total === 0 && !searching && (
                <div className="rounded-card border border-line bg-white px-4 py-10 text-center text-[13px] text-muted">
                  没有匹配的条款。试试用制度里的说法提问，例如「驳回意见」「加急认定」。
                </div>
              )}

              {result.hits.map((hit) => (
                <div key={`${hit.doc_id}-${hit.clause}`} className="rounded-card border border-line bg-white p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[14px] font-semibold text-ink">
                          《{hit.title}》{hit.version}
                        </span>
                        <ConfTag level={hit.confidentiality} />
                      </div>
                      <p className="mt-1 text-xs text-muted">{hit.breadcrumb}</p>
                    </div>
                    <span className="shrink-0 rounded bg-[#EEF2FF] px-2 py-1 text-[11px] font-medium text-primary">
                      相关度 {Math.round(hit.score * 100)}%
                    </span>
                  </div>

                  <p className="mt-3 whitespace-pre-wrap text-[13px] leading-6 text-ink-2">{hit.text}</p>

                  <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line-soft pt-2.5 text-[11px] text-faint">
                    <span>{hit.doc_id}</span>
                    <span>归口：{hit.department}</span>
                    {hit.effective_date && <span>生效：{String(hit.effective_date).slice(0, 10)}</span>}
                    <button
                      onClick={() => openPreview(hit.doc_id)}
                      className="ml-auto flex items-center gap-1 text-[11px] text-primary hover:underline"
                    >
                      <FileText className="h-3 w-3" /> 查看全文
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 未检索时的引导 */}
          {!result && !error && (
            <div className="flex items-start gap-3 rounded-card border border-dashed border-line bg-white px-5 py-5">
              <Sparkles className="mt-0.5 h-[18px] w-[18px] shrink-0 text-primary" />
              <div className="text-[13px] leading-6 text-ink-3">
                <p className="font-medium text-ink">这套知识库是用来回答「这单能不能过」的，不是文档仓库</p>
                <p className="mt-1 text-muted">
                  每份制度都带版本号、生效日和密级。检索时会自动排除已废止版本，并按登录人角色过滤——
                  所以同一句话，提交人和审批人看到的条文可能不一样，这是设计如此。
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ------------------------------------------------ 右：制度目录 */}
      <aside className="flex w-full shrink-0 flex-col border-t border-line bg-white lg:w-[320px] lg:overflow-y-auto lg:border-l lg:border-t-0">
        <div className="sticky top-0 z-10 border-b border-line-soft bg-white px-4 py-3.5">
          <div className="flex items-center justify-between">
            <h2 className="text-[15px] font-semibold text-ink">制度目录</h2>
            <span className="text-[11px] text-faint">
              可见 {docs?.visible ?? 0} / {docs?.total ?? 0}
            </span>
          </div>
          <p className="mt-1 text-[11px] text-muted">灰色带锁条目当前身份不可查看</p>
        </div>

        <div className="flex flex-col gap-4 px-4 py-3.5">
          {grouped.length === 0 && <p className="py-6 text-center text-xs text-faint">加载中…</p>}

          {grouped.map(([category, items]) => (
            <div key={category}>
              <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-faint">
                {category}
                <span className="font-normal normal-case">· {items.length} 份</span>
              </p>
              <ul className="flex flex-col">
                {items.map((d) => (
                  <li key={d.doc_id}>
                    <button
                      type="button"
                      onClick={() => openPreview(d.doc_id)}
                      className={cn(
                        'flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left transition-colors',
                        d.readable
                          ? 'hover:bg-[#F7F8FA]'
                          : 'opacity-55 hover:opacity-80 hover:bg-[#FFF7ED]',
                      )}
                      title={d.readable ? `点击预览《${d.title}》全文` : '密级不足，仍可点击查看拒绝原因'}
                    >
                    {d.readable ? (
                      <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-faint" />
                    ) : (
                      <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#C2410C]" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[12.5px] leading-5 text-ink-2">{d.title}</p>
                      <p className="truncate text-[10.5px] text-faint">
                        {d.version} · {d.chunks} 条 · {d.department}
                      </p>
                    </div>
                    <ConfTag level={d.confidentiality} />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </aside>

      {/* ------------------------------------------------ 全文预览抽屉 */}
      {preview && (
        <>
          <div className="fixed inset-0 z-40 bg-black/30" onClick={() => setPreview(null)} />
          <div className="fixed right-0 top-0 z-50 flex h-full w-[760px] max-w-[92vw] flex-col border-l border-line bg-white shadow-2xl">
            <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h2 className="truncate text-[16px] font-semibold text-ink">
                    {preview.data ? `《${preview.data.title}》${preview.data.version}` : preview.docId}
                  </h2>
                  {preview.data && <ConfTag level={preview.data.confidentiality} />}
                </div>
                {preview.data && (
                  <p className="mt-1 text-xs text-muted">
                    {preview.data.doc_id} · 归口 {preview.data.department} · 生效{' '}
                    {preview.data.effective_date ?? '—'} · {preview.data.char_count} 字
                  </p>
                )}
              </div>
              <button
                onClick={() => setPreview(null)}
                className="shrink-0 rounded-lg p-1.5 text-faint transition-colors hover:bg-[#F7F8FA] hover:text-ink"
                aria-label="关闭预览"
              >
                <X className="h-[18px] w-[18px]" />
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6">
              {preview.loading && <p className="py-10 text-center text-[13px] text-muted">正在打开…</p>}

              {preview.error && (
                <div className="mt-4 flex items-start gap-2.5 rounded-card border border-[#FECACA] bg-[#FEF2F2] px-4 py-3">
                  <Lock className="mt-0.5 h-4 w-4 shrink-0 text-[#B91C1C]" />
                  <div className="text-[13px] leading-6 text-[#B91C1C]">
                    <p className="font-medium">无法查看该制度全文</p>
                    <p className="mt-0.5">{preview.error}</p>
                    <p className="mt-2 text-[12px] text-[#991B1B]/80">
                      该限制由后端按密级拦截，不是前端隐藏。如需查阅，请联系档案管理员走借阅流程。
                    </p>
                  </div>
                </div>
              )}

              {preview.data && <MarkdownBody text={preview.data.body} />}
            </div>

            {preview.data && (
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line-soft px-5 py-2.5 text-[11px] text-faint">
                <span>状态：{preview.data.status === 'active' ? '现行有效' : preview.data.status}</span>
                <span>责任人：{preview.data.owner || '—'}</span>
                <span>适用单据：{preview.data.related_claims?.join('、') || '—'}</span>
                <span className="ml-auto">Esc 关闭</span>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
