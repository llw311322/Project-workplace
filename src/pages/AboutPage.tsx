import { useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  Coffee,
  Database,
  Layers,
  ShieldCheck,
} from 'lucide-react'
import { Button } from '@/components/ui/button'

/** 关键数字：全部来自实际运行结果，不做修饰 */
const METRICS = [
  { value: '32', unit: '份', label: '制度文档', hint: '覆盖 6 个业务域' },
  { value: '603', unit: '块', label: '条款切片', hint: '保留到「第 4.2 条」' },
  { value: '15', unit: '个', label: '业务接口', hint: '单据 11 + 知识库 4' },
  { value: '54', unit: '项', label: '自动化测试', hint: '全部通过' },
]

/** 岗位要求与实现对照 */
const JD_ROWS = [
  {
    require: 'Agent 应用开发',
    build: 'ReAct 循环 + 工具调用 + SSE 流式输出 + 超时降级',
    where: '单据详情页右侧栏，可直接对话',
  },
  {
    require: '业务工作台（表单 / 审批）',
    build: '4 个页面 + 状态机流转 + 四段式审批留痕',
    where: '草稿 → 提交 → 审批 / 驳回 → 历史',
  },
  {
    require: '对接内部系统',
    build: '适配层把前端契约映射到既有 Document 模型，零表结构改动',
    where: 'backend/app/routes/claims.py',
  },
  {
    require: '维护代码与部署说明',
    build: '单端口部署、测试覆盖、RAG 知识库台账与盘点命令',
    where: 'server/README.md · rag/README.md',
  },
]

/** 技术取舍：重点不是「做了什么」，而是「为什么这样选」 */
const DECISIONS = [
  {
    title: '加适配层，而不是改表结构',
    why: '后端原本只有通用的 Document(title, content)。前端需要结构化单据，最省事的做法是加字段，但那会让原有 Agent 与接口全部返工。',
    how: '在路由层做适配，把结构化字段序列化进 content 的 JSON 信封并带版本号 v1。原有代码零改动，出问题可整层回滚。',
    cost: '代价：无法用 SQL 按车间过滤，现在是应用层过滤。十万单以内可以接受，再往上应当迁独立表并建索引。',
  },
  {
    title: '知识库先用关键词，不上向量',
    why: '32 份制度、603 个条款块这个量级，向量检索的收益抵不过冷启动与嵌入成本。',
    how: '2-gram + IDF 关键词检索，实测 2ms 返回，且能精确命中「第 4.2 条」这类条款号——这恰恰是审批场景最需要的。',
    cost: '代价：同义改写会漏召回。检索接口已抽象成 Retriever，换 Chroma 不用改调用方。',
  },
  {
    title: '流式对话用 fetch 手写解析',
    why: 'EventSource 不支持 POST，也不能自定义 Header，而对话需要携带 JWT 和消息体。',
    how: 'fetch + ReadableStream 自行解析 data: 帧，同时兼容后端的 {event, data} 与常见的 {delta} 两种帧格式。',
    cost: '代价：要自己处理分包与断流。已加 done 标记与异常兜底。',
  },
  {
    title: '密级做在检索层，不做在前端',
    why: '前端隐藏按钮不叫权限，只叫界面。有人直接调接口就绕过去了。',
    how: '三道门控全部在服务端：时效（只答现行有效）、密级（阶梯式 ACL）、车间范围。命中前就被过滤，前端只拿到「被拦下几份」这个数字。',
    cost: '验证方式：点开受限制度会拿到后端返回的 403 原文，而不是前端拦下的提示。',
  },
  {
    title: 'AI 是辅助，不是卡点',
    why: '审批系统里最不能接受的是「模型挂了就批不了单」。',
    how: 'LLM 超时 5 秒即降级为本地规则校验，返回 degraded 标记，摘要与审批流程照常进行。',
    cost: '代价：降级时提示语质量下降。但业务连续性优先于文案完整度。',
  },
]

const DONE = [
  '单据全流程：草稿、提交、撤回、审批、驳回，每步留痕',
  '11 个单据接口 + 4 个知识库接口，含分页、筛选、关键字',
  'AI 摘要与合规校验，接真实 Qwen-Plus，超时降级为本地规则',
  'SSE 流式对话，逐字返回，断流有兜底',
  '32 份制度知识库，支持条款级引用与全文预览',
  '三道检索门控：时效、密级、车间范围',
  '54 项自动化测试覆盖接口、门控、限流、配额与删除回归',
  '删除单据前清理审批留痕，历史上的 500 已修复',
  '窄屏适配：侧边栏抽屉、列表卡片化、Agent 面板下移',
]

const KNOWN = [
  '线上部署为关键词检索：托管平台不提供外部数据库，pgvector 语义检索需自建服务器环境',
  'AI 校验仍以本地规则为主，尚未回填知识库条款引用',
  'Agent 工具仍是示例级（计算器、模拟搜索），业务工具待补',
  '制度草案中的金额与时限阈值标注为【待确认】，需业务方核定',
]

export default function AboutPage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      {/* 顶部条 */}
      <header className="sticky top-0 z-10 border-b border-line-soft bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1080px] items-center gap-2.5 px-5 sm:px-6">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary">
            <Coffee className="h-4 w-4 text-white" />
          </span>
          <span className="text-sm font-semibold text-ink">魔饮咖啡内部业务工作台</span>
          <span className="rounded-md bg-[#F1F2F6] px-2 py-0.5 text-[11px] text-muted">求职作品</span>
          <div className="flex-1" />
          <Button variant="ghost" size="sm" onClick={() => navigate('/login')}>
            登录页
          </Button>
          <Button size="sm" onClick={() => navigate('/login')}>
            进入演示 <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </header>

      {/* 封面 */}
      <section
        className="text-white"
        style={{ background: 'linear-gradient(135deg, #0A0D3A 0%, #262B8C 68%, #5966F2 100%)' }}
      >
        <div className="mx-auto max-w-[1080px] px-5 pb-14 pt-10 sm:px-6 sm:pt-16">
          <p className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-[11px] tracking-wide text-white/85">
            AI 全栈开发工程师 · 求职作品
          </p>
          <h1 className="mt-5 max-w-[720px] text-[30px] font-bold leading-[1.25] sm:text-[40px]">
            把一张纸质领料单，
            <br />
            做成 Agent 能读懂、能校验、能追溯的线上流程
          </h1>
          <p className="mt-4 max-w-[620px] text-[14px] leading-7 text-navy-text">
            面向魔饮咖啡（青岛）工厂的真实业务场景：货品申领、多级审批、制度检索、AI 辅助。
            所有页面均可交互，数据为虚构演示数据。
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <Button
              size="lg"
              className="h-11 bg-white px-5 text-sm text-primary hover:bg-white/90"
              onClick={() => navigate('/login')}
            >
              以面试官身份进入 <ArrowRight className="h-4 w-4" />
            </Button>
            <a
              href="#decisions"
              className="inline-flex h-11 items-center rounded-lg border border-white/25 px-5 text-sm text-white/90 hover:bg-white/10"
            >
              看技术取舍
            </a>
          </div>

          {/* 数字 */}
          <div className="mt-12 grid grid-cols-2 gap-3 lg:grid-cols-4">
            {METRICS.map((m) => (
              <div key={m.label} className="rounded-xl bg-white/[0.08] p-4">
                <p className="text-[26px] font-bold leading-none">
                  {m.value}
                  <span className="ml-1 text-xs font-normal text-white/60">{m.unit}</span>
                </p>
                <p className="mt-2 text-[13px] font-medium text-white/90">{m.label}</p>
                <p className="mt-0.5 text-[11px] text-white/55">{m.hint}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <main className="mx-auto max-w-[1080px] px-5 py-10 sm:px-6 sm:py-14">
        {/* 岗位对照 */}
        <section>
          <SectionTitle
            eyebrow="01"
            title="这份岗位要求，我对应做了什么"
            desc="需求来自岗位描述里的四条能力要求，右边是可以在演示中点进去验证的位置。"
          />
          <div className="mt-6 overflow-hidden rounded-xl border border-line-soft bg-white">
            <div className="hidden grid-cols-[210px_1fr_240px] gap-4 border-b border-line-soft bg-[#FAFBFC] px-5 py-2.5 text-[11px] font-medium text-faint lg:grid">
              <span>岗位要求</span>
              <span>我的实现</span>
              <span>可在哪里验证</span>
            </div>
            {JD_ROWS.map((row, i) => (
              <div
                key={row.require}
                className={`grid gap-1.5 px-5 py-4 lg:grid-cols-[210px_1fr_240px] lg:items-start lg:gap-4 ${
                  i > 0 ? 'border-t border-line-soft' : ''
                }`}
              >
                <p className="text-[13px] font-semibold text-ink">{row.require}</p>
                <p className="text-[13px] leading-6 text-ink-2">{row.build}</p>
                <p className="text-[12px] leading-5 text-muted lg:text-right">{row.where}</p>
              </div>
            ))}
          </div>
        </section>

        {/* 架构 */}
        <section className="mt-14">
          <SectionTitle
            eyebrow="02"
            title="系统架构"
            desc="单端口部署：同一个进程既提供前端页面，也提供 API；知识库与业务库都在服务内，不依赖外部中间件。"
          />
          <div className="mt-6 rounded-xl border border-line-soft bg-white p-5">
            <div className="flex flex-col items-stretch gap-2.5">
              <LayerRow
                icon={Layers}
                title="浏览器 · React 18 + TypeScript + Tailwind"
                desc="4 个业务页面 + 知识库问答页；fetch + ReadableStream 解析 SSE"
                tone="light"
              />
              <Arrow />
              <LayerRow
                icon={ShieldCheck}
                title="FastAPI · 单端口 8001"
                desc="JWT 鉴权 · 限流 · 异常统一封装 · 静态资源托管与 SPA 回落"
                tone="primary"
              />
              <Arrow />
              <div className="grid gap-2.5 lg:grid-cols-3">
                <LayerRow
                  icon={BrainCircuit}
                  title="Agent 层"
                  desc="ReAct 循环、工具调用、摘要与校验、超时降级"
                />
                <LayerRow
                  icon={Database}
                  title="数据层"
                  desc="SQLite（开发）/ PostgreSQL + pgvector（生产预留）"
                />
                <LayerRow
                  icon={Coffee}
                  title="知识库"
                  desc="32 份制度 md + 三道门控 + 条款级引用"
                />
              </div>
            </div>
          </div>
        </section>

        {/* 技术取舍 */}
        <section id="decisions" className="mt-14 scroll-mt-16">
          <SectionTitle
            eyebrow="03"
            title="五个关键取舍"
            desc="能跑起来只是及格线。这里写清每个选择放弃了什么，以及什么规模下应该换方案。"
          />
          <div className="mt-6 grid gap-3 lg:grid-cols-2">
            {DECISIONS.map((d, i) => (
              <div key={d.title} className="rounded-xl border border-line-soft bg-white p-5">
                <div className="flex items-start gap-2.5">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-primary-light text-[11px] font-semibold text-primary">
                    {i + 1}
                  </span>
                  <p className="text-[14px] font-semibold leading-6 text-ink">{d.title}</p>
                </div>
                <div className="mt-3 space-y-2 pl-[30px]">
                  <p className="text-[12px] leading-6 text-ink-2">
                    <span className="text-faint">为什么：</span>
                    {d.why}
                  </p>
                  <p className="text-[12px] leading-6 text-ink-2">
                    <span className="text-faint">怎么做：</span>
                    {d.how}
                  </p>
                  <p className="text-[12px] leading-6 text-muted">{d.cost}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 完成与未完成 */}
        <section className="mt-14">
          <SectionTitle
            eyebrow="04"
            title="做完了什么，没做什么"
            desc="没做完的部分一样写在明面上——比起「全部完成」，我更愿意把边界交代清楚。"
          />
          <div className="mt-6 grid gap-3 lg:grid-cols-2">
            <div className="rounded-xl border border-line-soft bg-white p-5">
              <p className="flex items-center gap-2 text-[13px] font-semibold text-ink">
                <CheckCircle2 className="h-4 w-4 text-[#16A34A]" /> 已实现
              </p>
              <ul className="mt-3 space-y-2">
                {DONE.map((t) => (
                  <li key={t} className="flex gap-2 text-[12px] leading-6 text-ink-2">
                    <span className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-[#16A34A]" />
                    {t}
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-xl border border-line-soft bg-white p-5">
              <p className="flex items-center gap-2 text-[13px] font-semibold text-ink">
                <AlertCircle className="h-4 w-4 text-[#D97706]" /> 已知未做 / 存在问题
              </p>
              <ul className="mt-3 space-y-2">
                {KNOWN.map((t) => (
                  <li key={t} className="flex gap-2 text-[12px] leading-6 text-ink-2">
                    <span className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-[#D97706]" />
                    {t}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* 演示动线 */}
        <section className="mt-14">
          <SectionTitle
            eyebrow="05"
            title="三步看完核心能力"
            desc="不用注册，点一下就以面试官身份进入（默认审批人视角，权限最高）。"
          />
          <div className="mt-6 grid gap-3 lg:grid-cols-3">
            {[
              {
                step: '第一步',
                title: '看表单与 AI 校验',
                desc: '新建申领单，故意只填一半就提交，观察拦截提示；填完提交，右侧栏问 AI 这单有什么风险。',
                to: '/claims/new',
              },
              {
                step: '第二步',
                title: '看审批与留痕',
                desc: '切到待审批，打开单据驳回——意见留空会报错，因为制度要求驳回必须写明理由。',
                to: '/pending',
              },
              {
                step: '第三步',
                title: '看知识库与权限',
                desc: '进制度知识库点「驳回必须写意见吗」，答案会指到具体条款；再用员工账号看，结果会变少。',
                to: '/kb',
              },
            ].map((s) => (
              <div key={s.step} className="flex flex-col rounded-xl border border-line-soft bg-white p-5">
                <p className="text-[11px] font-medium text-primary">{s.step}</p>
                <p className="mt-1.5 text-[14px] font-semibold text-ink">{s.title}</p>
                <p className="mt-2 flex-1 text-[12px] leading-6 text-muted">{s.desc}</p>
                <Button variant="text" size="sm" className="mt-3 justify-start" onClick={() => navigate('/login')}>
                  进入体验 <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        </section>

        {/* 技术栈 */}
        <section className="mt-14 rounded-xl border border-line-soft bg-white p-5">
          <p className="text-[13px] font-semibold text-ink">技术栈</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {[
              'React 18',
              'TypeScript',
              'Vite 5',
              'Tailwind CSS 3',
              'FastAPI',
              'SQLAlchemy 2 (async)',
              'LangChain 0.3',
              'Qwen-Plus（百炼）',
              'SQLite / PostgreSQL + pgvector',
              'JWT',
              'SSE',
              'pytest',
            ].map((t) => (
              <span key={t} className="rounded-md bg-[#F3F4F7] px-2.5 py-1 text-[12px] text-ink-2">
                {t}
              </span>
            ))}
          </div>
          <p className="mt-4 border-t border-line-soft pt-4 text-[12px] leading-6 text-faint">
            说明：本作品中的企业信息、单据与制度均为虚构演示内容，仅用于展示工程实现；制度草案中的金额与时限阈值标注为【待确认】，需业务方核定后方可正式施行。
          </p>
        </section>
      </main>

      <footer className="border-t border-line-soft bg-white py-8">
        <div className="mx-auto flex max-w-[1080px] flex-col items-start justify-between gap-3 px-6 sm:flex-row sm:items-center">
          <p className="text-[12px] text-faint">魔饮咖啡内部业务工作台 · 求职作品演示</p>
          <Button size="sm" onClick={() => navigate('/login')}>
            进入演示 <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </footer>
    </div>
  )
}

function SectionTitle({ eyebrow, title, desc }: { eyebrow: string; title: string; desc: string }) {
  return (
    <div>
      <p className="text-[11px] font-semibold tracking-widest text-primary">{eyebrow}</p>
      <h2 className="mt-2 text-[22px] font-bold leading-8 text-ink">{title}</h2>
      <p className="mt-2 max-w-[720px] text-[13px] leading-6 text-muted">{desc}</p>
    </div>
  )
}

function LayerRow({
  icon: Icon,
  title,
  desc,
  tone = 'light',
}: {
  icon: typeof Layers
  title: string
  desc: string
  tone?: 'light' | 'primary'
}) {
  const isPrimary = tone === 'primary'
  return (
    <div
      className={`flex items-start gap-3 rounded-lg border p-3.5 ${
        isPrimary ? 'border-primary/30 bg-primary-light' : 'border-line-soft bg-[#FAFBFC]'
      }`}
    >
      <span
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${
          isPrimary ? 'bg-primary text-white' : 'bg-white text-ink-2 ring-1 ring-line-soft'
        }`}
      >
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0">
        <p className={`text-[13px] font-semibold ${isPrimary ? 'text-primary-deep' : 'text-ink'}`}>{title}</p>
        <p className={`mt-0.5 text-[11px] leading-5 ${isPrimary ? 'text-primary-ink' : 'text-muted'}`}>{desc}</p>
      </div>
    </div>
  )
}

function Arrow() {
  return (
    <div className="flex justify-center">
      <span className="h-3 w-px bg-line-soft" />
    </div>
  )
}
