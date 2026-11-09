/** 与后端 Pydantic 模型一一对应的类型定义 */

export type Role = 'submitter' | 'approver'

/** 草稿 → 已提交(待审批) → 审批中 → 审批通过 / 已驳回 */
export type ClaimStatus = 'draft' | 'submitted' | 'approving' | 'approved' | 'rejected'

export type Urgency = 'normal' | 'urgent'

export interface User {
  id: string
  account: string
  name: string
  role: Role
  /** 所属车间 / 部门（如：萃取车间、城阳工厂） */
  workshop?: string
  title?: string
}

export interface LoginPayload {
  account: string
  password: string
  role: Role
}

export interface LoginResult {
  token: string
  user: User
}

export interface ClaimItem {
  id: string
  name: string
  spec: string
  quantity: number
  unit: string
  purpose: string
}

export interface Claim {
  id: string
  code: string
  title: string
  /** 申领车间 / 部门 */
  workshop: string
  workshopCode: string
  applicant: string
  applicantTitle: string
  phone: string
  demandDate: string
  urgency: Urgency
  remark: string
  status: ClaimStatus
  items: ClaimItem[]
  submittedAt?: string | null
  createdAt: string
  updatedAt: string
  approver?: string
}

export type ApprovalAction = 'submit' | 'withdraw' | 'approve' | 'reject' | 'ai_validate' | 'create'

export interface ApprovalRecord {
  id: string
  action: ApprovalAction
  operator: string
  operatorRole: Role | 'system'
  comment?: string
  createdAt: string
  /** Agent 插件产生的留痕，需要在 UI 上单独标注 */
  fromAgent?: boolean
  fromStatus?: ClaimStatus
  toStatus?: ClaimStatus
}

export interface ClaimListQuery {
  status?: ClaimStatus | 'all'
  workshop?: string
  keyword?: string
  startDate?: string
  endDate?: string
  page?: number
  pageSize?: number
}

export interface PageResult<T> {
  list: T[]
  total: number
  page: number
  pageSize: number
}

/** 单据 AI 摘要 */
export interface ClaimSummary {
  summary: string
  highlights: string[]
  degraded?: boolean
}

/** 单据 AI 校验 */
export interface ClaimValidation {
  passed: boolean
  message: string
  issues: string[]
  missingFields: string[]
  degraded?: boolean
}

/** 统一返回体 */
export interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
  traceId?: string
}

/** SSE 单个事件 */
export interface ChatDelta {
  delta?: string
  content?: string
  text?: string
  done?: boolean
}

/* --------------------------------------------------------------- 知识库 */

export type Confidentiality = 'public' | 'internal' | 'restricted' | 'secret'

/** 知识库体检 */
export interface KbStats {
  available: boolean
  message?: string
  total_expected: number
  total_loaded: number
  coverage: number
  chunks: number
  categories: { category: string; docs: number; chunks: number }[]
  visible_docs: number
  total_docs: number
  stale: { doc_id: string; version: string; title: string }[]
  /** 三道门控的说明，页面直接展示 */
  gates: { key: string; desc: string }[]
}

/** 制度清单条目 */
export interface KbDoc {
  doc_id: string
  title: string
  version: string
  category: string
  doc_type: string
  department: string
  confidentiality: Confidentiality
  effective_date: string | null
  expire_date: string | null
  status: string
  chunks: number
  related_claims: string[]
  /** 当前登录身份是否可读（false = 被密级拦下） */
  readable: boolean
}

export interface KbDocResult {
  available: boolean
  list: KbDoc[]
  total: number
  visible: number
}

/** 命中条款 */
export interface KbHit {
  score: number
  doc_id: string
  title: string
  version: string
  category: string
  department: string
  confidentiality: Confidentiality
  effective_date: string | null
  clause: string
  section: string
  /** 「《规定》v1.0 > 第四章 > 第 4.2 条」 */
  breadcrumb: string
  text: string
}

export interface KbSearchResult {
  query: string
  hits: KbHit[]
  total: number
  elapsed_ms: number
  /** 本次因密级/ACL 被拦下的制度份数 */
  suppressed_docs: number
  viewer_role: string
}

/** 制度全文（预览用） */
export interface KbDocDetail {
  doc_id: string
  title: string
  version: string
  category: string
  doc_type: string
  department: string
  confidentiality: Confidentiality
  effective_date: string | null
  expire_date: string | null
  status: string
  owner: string
  related_claims: string[]
  keywords: string[]
  body: string
  char_count: number
}

export interface ChatStreamOptions {
  onDelta: (chunk: string) => void
  onDone?: () => void
  signal?: AbortSignal
}
