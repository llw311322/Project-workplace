import axios, { type AxiosRequestConfig } from 'axios'
import { session } from './auth'
import { mock } from './mock'
import type {
  ApiEnvelope,
  ApprovalRecord,
  ChatStreamOptions,
  Claim,
  ClaimListQuery,
  ClaimSummary,
  ClaimValidation,
  KbDocDetail,
  KbDocResult,
  KbSearchResult,
  KbStats,
  LoginPayload,
  LoginResult,
  PageResult,
} from './types'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) || '/api'
/** 后端未就绪时默认走内置 mock，联调时把 .env 的 VITE_USE_MOCK 改为 false */
const USE_MOCK = (import.meta.env.VITE_USE_MOCK ?? 'true') !== 'false'
const AGENT_DEGRADE = (import.meta.env.VITE_ENABLE_AGENT_DEGRADE ?? 'true') !== 'false'

export class ApiError extends Error {
  code: number
  constructor(message: string, code = -1) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

export const http = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use((config) => {
  const token = session.getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
    // 托管平台的网关会改写 Authorization 头，token 需要同时走自定义头
    config.headers['X-Auth-Token'] = token
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      session.clear()
      if (!location.pathname.startsWith('/login')) location.href = '/login'
      return Promise.reject(new ApiError('登录已过期，请重新登录', 401))
    }
    const message =
      error.response?.data?.message || error.response?.data?.detail || error.message || '网络异常，请稍后重试'
    return Promise.reject(new ApiError(String(message), error.response?.status ?? -1))
  },
)

/** 统一返回体拆包：{ code, message, data } */
async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const res = await http.request<ApiEnvelope<T> | T>(config)
  const body = res.data as ApiEnvelope<T>
  if (body && typeof body === 'object' && 'code' in body) {
    if (body.code !== 0 && body.code !== 200) {
      throw new ApiError(body.message || '请求失败', body.code)
    }
    return body.data
  }
  return res.data as T
}

/* ------------------------------------------------------------------ 登录 */

export const authApi = {
  async login(payload: LoginPayload): Promise<LoginResult> {
    if (USE_MOCK) return mock.login(payload)
    // 后端契约：POST /auth/login {username,password} → {access_token}，
    // 用户资料要再取 GET /auth/me；角色由后端数据决定，前端不再传 role。
    const tokens = await request<{ access_token: string; token_type: string; expires_at: string }>({
      url: '/auth/login',
      method: 'POST',
      data: { username: payload.account, password: payload.password },
    })
    const me = await request<{
      id: number
      username: string
      display_name?: string | null
      role: string
    }>({
      url: '/auth/me',
      method: 'GET',
      headers: { Authorization: `Bearer ${tokens.access_token}`, 'X-Auth-Token': tokens.access_token },
    })
    return {
      token: tokens.access_token,
      user: {
        id: String(me.id),
        account: me.username,
        // 后端 display_name 形如「张三（提交人）」，去掉括号内的角色后缀
        name: (me.display_name || me.username).replace(/（.*?）/g, '').trim(),
        // 后端可能是 submitter / approver / admin，admin 按审批人处理
        role: me.role === 'submitter' ? 'submitter' : 'approver',
      },
    }
  },
  async logout(): Promise<void> {
    if (USE_MOCK) return
    await request<void>({ url: '/auth/logout', method: 'POST' }).catch(() => undefined)
  },
}

/* ------------------------------------------------------------- 单据 / 审批 */

export const claimApi = {
  /** 我的提交单据列表 GET /claims/mine */
  async listMine(query: ClaimListQuery): Promise<PageResult<Claim>> {
    if (USE_MOCK) return mock.listMine(query)
    return request<PageResult<Claim>>({ url: '/claims/mine', method: 'GET', params: query })
  },

  /** 我的待审批列表 GET /claims/pending */
  async listPending(query: ClaimListQuery): Promise<PageResult<Claim>> {
    if (USE_MOCK) return mock.listPending(query)
    return request<PageResult<Claim>>({ url: '/claims/pending', method: 'GET', params: query })
  },

  /** 单据详情 GET /claims/{id} */
  async detail(id: string): Promise<Claim> {
    if (USE_MOCK) return mock.get(id)
    return request<Claim>({ url: `/claims/${id}`, method: 'GET' })
  },

  /** 新建草稿 POST /claims */
  async create(payload: Partial<Claim>): Promise<Claim> {
    if (USE_MOCK) return mock.create(payload)
    return request<Claim>({ url: '/claims', method: 'POST', data: payload })
  },

  /** 保存草稿 PUT /claims/{id} */
  async saveDraft(id: string, payload: Partial<Claim>): Promise<Claim> {
    if (USE_MOCK) return mock.saveDraft(id, payload)
    return request<Claim>({ url: `/claims/${id}`, method: 'PUT', data: payload })
  },

  /** 提交单据 POST /claims/{id}/submit */
  async submit(id: string): Promise<Claim> {
    if (USE_MOCK) return mock.submit(id)
    return request<Claim>({ url: `/claims/${id}/submit`, method: 'POST' })
  },

  /** 撤销提交 POST /claims/{id}/withdraw */
  async withdraw(id: string): Promise<Claim> {
    if (USE_MOCK) return mock.withdraw(id)
    return request<Claim>({ url: `/claims/${id}/withdraw`, method: 'POST' })
  },

  /** 同意 POST /claims/{id}/approve */
  async approve(id: string, comment?: string): Promise<Claim> {
    if (USE_MOCK) return mock.approve(id, comment)
    return request<Claim>({ url: `/claims/${id}/approve`, method: 'POST', data: { comment } })
  },

  /** 驳回 POST /claims/{id}/reject */
  async reject(id: string, comment: string): Promise<Claim> {
    if (USE_MOCK) return mock.reject(id, comment)
    return request<Claim>({ url: `/claims/${id}/reject`, method: 'POST', data: { comment } })
  },

  /** 审批历史 GET /claims/{id}/history */
  async history(id: string): Promise<ApprovalRecord[]> {
    if (USE_MOCK) return mock.history(id)
    return request<ApprovalRecord[]>({ url: `/claims/${id}/history`, method: 'GET' })
  },
}

/* --------------------------------------------------------------- Agent 能力 */

/**
 * Agent 仅为辅助插件：
 * 任何异常都不向上抛给业务主流程，返回 degraded 标记，由 UI 提示降级。
 */
export const agentApi = {
  /** 单据 AI 摘要 POST /agent/claims/summary */
  async summary(claim: Partial<Claim>): Promise<ClaimSummary> {
    try {
      if (USE_MOCK) return await mock.summary(claim)
      return await request<ClaimSummary>({ url: '/agent/claims/summary', method: 'POST', data: claim, timeout: 20000 })
    } catch (err) {
      if (!AGENT_DEGRADE) throw err
      return {
        summary: 'AI 摘要暂时不可用，请手动核对单据内容。',
        highlights: [],
        degraded: true,
      }
    }
  },

  /** 单据 AI 校验 POST /agent/claims/validate */
  async validate(claim: Partial<Claim>): Promise<ClaimValidation> {
    try {
      if (USE_MOCK) return await mock.validate(claim)
      return await request<ClaimValidation>({
        url: '/agent/claims/validate',
        method: 'POST',
        data: claim,
        timeout: 20000,
      })
    } catch (err) {
      if (!AGENT_DEGRADE) throw err
      return {
        passed: true,
        message: 'AI 校验服务暂时不可用，已跳过自动校验',
        issues: [],
        missingFields: [],
        degraded: true,
      }
    }
  },

  /**
   * 流式对话 POST /agent/chat/stream
   * EventSource 不支持 POST，这里用 fetch + ReadableStream 解析 SSE。
   */
  async chatStream(
    payload: { claimId?: string; question: string },
    options: ChatStreamOptions,
  ): Promise<void> {
    if (USE_MOCK) {
      await mock.chatStream(payload, options.onDelta, options.signal)
      options.onDone?.()
      return
    }

    const url = `${BASE_URL.replace(/\/$/, '')}/agent/chat/stream`
    const token = session.getToken()
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}`, 'X-Auth-Token': token } : {}),
      },
      // 后端字段是 claim_id：带上后模型才能看到当前单据内容（否则只会答"未提交单据内容"）
      body: JSON.stringify({
        question: payload.question,
        claim_id: payload.claimId || undefined,
      }),
      signal: options.signal,
    })

    if (!res.ok || !res.body) {
      throw new ApiError(`AI 对话连接失败（${res.status}）`, res.status)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const events = buffer.split(/\r?\n\r?\n/)
      buffer = events.pop() ?? ''

      for (const event of events) {
        const data = event
          .split(/\r?\n/)
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trim())
          .join('\n')

        if (!data) continue
        if (data === '[DONE]') {
          options.onDone?.()
          return
        }

        let chunk = data
        try {
          const parsed = JSON.parse(data) as {
            delta?: string
            content?: string
            text?: string
            done?: boolean
            event?: string
            data?: unknown
          }

          // 后端 FastAPI 的帧格式：{ "event": "start|token|done|error", "data": "字" }
          if (parsed.event) {
            if (parsed.event === 'start') continue
            if (parsed.event === 'done') {
              options.onDone?.()
              return
            }
            if (parsed.event === 'error') {
              const tip = typeof parsed.data === 'string' ? parsed.data : ''
              if (tip) options.onDelta(tip)
              options.onDone?.()
              return
            }
            // token 帧
            chunk =
              typeof parsed.data === 'string'
                ? parsed.data
                : ((parsed.data as { delta?: string })?.delta ?? '')
          } else {
            if (parsed.done) {
              options.onDone?.()
              return
            }
            chunk = parsed.delta ?? parsed.content ?? parsed.text ?? ''
          }
        } catch {
          // 纯文本事件，直接使用
        }
        if (chunk) options.onDelta(chunk)
      }
    }
    options.onDone?.()
  },
}

/* --------------------------------------------------------------- 制度知识库 */

/** USE_MOCK 时的占位返回，保证没接后端也能看到页面结构 */
const KB_MOCK_STATS: KbStats = {
  available: true,
  total_expected: 32,
  total_loaded: 32,
  coverage: 100,
  chunks: 603,
  categories: [
    { category: '01_制度流程', docs: 7, chunks: 152 },
    { category: '02_质量合规', docs: 9, chunks: 198 },
    { category: '03_生产SOP', docs: 6, chunks: 121 },
    { category: '04_供应链与客户', docs: 4, chunks: 64 },
    { category: '05_人事培训', docs: 4, chunks: 45 },
    { category: '06_财务采购', docs: 2, chunks: 23 },
  ],
  visible_docs: 31,
  total_docs: 32,
  stale: [],
  gates: [
    { key: '时效', desc: '只检索已生效且未废止的制度版本' },
    { key: '密级', desc: '按登录人角色过滤，配方类对提交人不可见' },
    { key: '车间', desc: '车间专属参数不跨车间检索' },
  ],
}

export const kbApi = {
  /** 知识库体检 GET /kb/stats */
  async stats(): Promise<KbStats> {
    if (USE_MOCK) return KB_MOCK_STATS
    return request<KbStats>({ url: '/kb/stats', method: 'GET' })
  },

  /** 制度清单 GET /kb/docs */
  async docs(): Promise<KbDocResult> {
    if (USE_MOCK) return { available: true, list: [], total: 0, visible: 0 }
    return request<KbDocResult>({ url: '/kb/docs', method: 'GET' })
  },

  /** 条款检索 POST /kb/search */
  async search(query: string, topK = 6): Promise<KbSearchResult> {
    if (USE_MOCK) {
      return { query, hits: [], total: 0, elapsed_ms: 0, suppressed_docs: 0, viewer_role: 'approver' }
    }
    return request<KbSearchResult>({
      url: '/kb/search',
      method: 'POST',
      data: { query, top_k: topK },
      timeout: 15000,
    })
  },

  /**
   * 制度全文预览 GET /kb/doc/{docId}
   * 密级不足时后端返回 403，message 里会说明密级与当前身份，直接展示给用户。
   */
  async docDetail(docId: string): Promise<KbDocDetail> {
    if (USE_MOCK) throw new ApiError('演示模式未接入知识库，请关闭 VITE_USE_MOCK', 400)
    return request<KbDocDetail>({ url: `/kb/doc/${encodeURIComponent(docId)}`, method: 'GET' })
  },
}

export { USE_MOCK, AGENT_DEGRADE }
