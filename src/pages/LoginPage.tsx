import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Coffee, Eye, EyeOff, Sparkles, UserCheck } from 'lucide-react'
import { authApi } from '@/lib/api'
import { session } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import type { Role } from '@/lib/types'

const FEATURES = [
  { title: '单据全流程', desc: '草稿到审批通过，每一步留痕可追溯' },
  { title: 'AI 智能辅助', desc: '自动摘要、内容校验，AI 降级不影响业务' },
  { title: '知识库问答', desc: '工厂制度、产品规格资料，随问随答' },
]

export default function LoginPage() {
  const navigate = useNavigate()
  const [role, setRole] = useState<Role>('submitter')
  const [account, setAccount] = useState('0001')
  const [password, setPassword] = useState('123456')
  const [showPwd, setShowPwd] = useState(false)
  const [remember, setRemember] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!account.trim() || !password) {
      setError('请输入工号与密码')
      return
    }
    setLoading(true)
    setError('')
    try {
      const { token, user } = await authApi.login({ account: account.trim(), password, role })
      session.save(token, user)
      navigate('/claims', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  /** 面试官一键进入：直接用审批人账号登录，免去手输账号密码 */
  const enterAsInterviewer = async () => {
    setLoading(true)
    setError('')
    try {
      const { token, user } = await authApi.login({
        account: '1001',
        password: '123456',
        role: 'approver',
      })
      session.save(token, user)
      navigate('/claims', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : '进入失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen w-full bg-navy">
      {/* 左侧品牌区 */}
      <div
        className="hidden flex-1 flex-col p-14 lg:flex"
        style={{
          background:
            'linear-gradient(135deg, #0A0D3A 0%, #262B8C 70%, #5966F2 100%)',
        }}
      >
        <div className="flex items-center gap-3">
          <span className="flex h-[34px] w-[34px] items-center justify-center rounded-lg bg-white/15">
            <Coffee className="h-5 w-5 text-white" />
          </span>
          <span className="text-xl font-bold text-white">魔饮咖啡 MOINS COFFEE</span>
        </div>
        <p className="mt-2 text-xs text-navy-muted">
          乐饮创新科技集团旗下 · 魔饮咖啡（青岛）有限公司
        </p>

        <div className="flex-1" />

        <h1 className="text-[44px] font-bold leading-tight text-white">内部业务工作台</h1>
        <p className="mt-3 text-base text-navy-text">
          货品申领 · 审批流转 · AI 智能辅助 · 知识库问答
        </p>

        <div className="mt-10 flex gap-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="flex-1 rounded-xl bg-white/[0.07] p-4">
              <p className="text-sm font-medium text-white">{f.title}</p>
              <p className="mt-1.5 text-xs leading-5 text-navy-muted">{f.desc}</p>
            </div>
          ))}
        </div>

        <p className="mt-12 text-xs leading-5 text-navy-muted">
          作品演示环境 · 页面数据均为虚构
          <br />
          城阳工厂：青岛市城阳区天风北路 366 号
        </p>
      </div>

      {/* 右侧登录表单 */}
      <div className="flex w-full flex-col justify-center gap-4 overflow-y-auto bg-white px-5 py-8 sm:px-10 lg:w-[480px] lg:shrink-0 lg:px-14">
        {/* 求职作品入口：让面试官一进来就知道这是什么，并能跳过手输账号 */}
        <div className="rounded-xl border border-[#DDE2FB] bg-[#F6F7FE] p-4">
          <div className="flex items-center gap-2">
            <UserCheck className="h-4 w-4 text-primary" />
            <p className="text-[13px] font-semibold text-ink">求职作品 · 演示环境</p>
          </div>
          <p className="mt-1.5 text-xs leading-5 text-muted">
            面向「AI 全栈开发工程师」岗位。数据均为虚构，可任意操作。
          </p>
          <div className="mt-3 flex gap-2">
            <Button onClick={enterAsInterviewer} className="h-9 flex-1" disabled={loading}>
              {loading ? '进入中…' : '以面试官身份进入'}
            </Button>
            <Button variant="secondary" onClick={() => navigate('/about')} className="h-9">
              项目说明
            </Button>
          </div>
        </div>

        <div>
          <h2 className="text-[26px] font-bold text-ink">登录工作台</h2>
          <p className="mt-1.5 text-[13px] text-muted">使用企业工号登录，账号由管理员开通</p>
        </div>

        <form className="flex flex-col gap-4" onSubmit={submit}>
          <div>
            <p className="mb-1.5 text-[13px] font-medium text-ink-2">登录角色</p>
            <div className="flex gap-3">
              {(
                [
                  { key: 'submitter', label: '员工' },
                  { key: 'approver', label: '审批人' },
                ] as const
              ).map((opt) => (
                <button
                  key={opt.key}
                  type="button"
                  onClick={() => {
                    setRole(opt.key)
                    // 演示环境：切换角色时带出对应种子账号
                    setAccount(opt.key === 'submitter' ? '0001' : '1001')
                  }}
                  className={cn(
                    'flex h-11 flex-1 items-center justify-center gap-2 rounded-[10px] text-sm transition-colors',
                    role === opt.key
                      ? 'border-2 border-primary bg-primary-light font-medium text-primary'
                      : 'border border-field-border bg-white text-muted hover:border-faint',
                  )}
                >
                  <span
                    className={cn(
                      'h-2 w-2 rounded-full',
                      role === opt.key ? 'bg-primary' : 'bg-[#D1D5DB]',
                    )}
                  />
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-1.5 text-[13px] font-medium text-ink-2">工号 / 账号</p>
            <Input value={account} onChange={(e) => setAccount(e.target.value)} placeholder="请输入企业工号" autoComplete="username" />
          </div>

          <div>
            <p className="mb-1.5 text-[13px] font-medium text-ink-2">密码</p>
            <div className="relative">
              <Input
                type={showPwd ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="请输入密码"
                autoComplete="current-password"
                className="pr-10"
              />
              <button
                type="button"
                onClick={() => setShowPwd((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-faint hover:text-muted"
              >
                {showPwd ? <EyeOff className="h-[18px] w-[18px]" /> : <Eye className="h-[18px] w-[18px]" />}
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between">
            <label className="flex cursor-pointer items-center gap-2 text-[13px] text-muted">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="h-4 w-4 rounded border-field-border accent-primary"
              />
              记住登录状态
            </label>
            <button type="button" className="text-[13px] text-primary hover:underline">
              忘记密码？
            </button>
          </div>

          {error && (
            <p className="rounded-lg bg-[#FEE2E2] px-3 py-2 text-[13px] text-[#B91C1C]">{error}</p>
          )}

          <Button type="submit" size="lg" className="h-12 w-full text-[15px]" disabled={loading}>
            {loading ? '登录中…' : '登 录'}
          </Button>

          <p className="text-center text-xs leading-5 text-faint">
            演示工号：0001（张三·员工） / 1001（李四·审批人），密码均为 123456
          </p>

          <p className="text-center text-xs leading-5 text-faint">
            登录即代表同意《内部系统使用规范》，如遇问题请联系 IT 服务台
          </p>
        </form>

        <p className="flex items-center gap-1.5 text-xs text-faint lg:hidden">
          <Sparkles className="h-3.5 w-3.5" /> 建议在桌面端使用，以获得完整后台体验
        </p>
      </div>
    </div>
  )
}
