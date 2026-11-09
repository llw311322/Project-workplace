import type {
  ApprovalRecord,
  Claim,
  ClaimListQuery,
  ClaimSummary,
  ClaimValidation,
  LoginPayload,
  LoginResult,
  PageResult,
  User,
} from './types'

/** 后端未就绪时使用的内置数据，所有写操作在内存中生效，刷新页面后复位 */
const delay = (ms = 320) => new Promise((resolve) => setTimeout(resolve, ms))

const USERS: Record<string, User> = {
  MY1024: {
    id: 'u-1024',
    account: 'MY1024',
    name: '林晓',
    role: 'approver',
    workshop: '城阳工厂',
    title: '生产经理',
  },
  MY2088: {
    id: 'u-2088',
    account: 'MY2088',
    name: '张伟',
    role: 'submitter',
    workshop: '萃取车间',
    title: '车间主管',
  },
}

const claim012: Claim = {
  id: 'c-012',
  code: 'MO-20261103-012',
  title: '11月出口订单备料（冷萃咖啡液产线）',
  workshop: '萃取车间',
  workshopCode: 'EX-01',
  applicant: '张伟',
  applicantTitle: '车间主管',
  phone: '138****6688',
  demandDate: '2026-11-08',
  urgency: 'normal',
  remark:
    '对应美国客户订单 PO-2611-03，请于本周五（11/7）前送达产线，生豆运输注意防潮避光。到货后由车间领班当场验收并在系统确认。',
  status: 'submitted',
  createdAt: '2026-10-29T15:20:00+08:00',
  updatedAt: '2026-11-03T09:12:00+08:00',
  submittedAt: '2026-11-03T09:12:00+08:00',
  approver: '李四',
  items: [
    { id: 'i-1', name: '埃塞俄比亚水洗生咖啡豆 G1', spec: '60kg / 袋', quantity: 24, unit: '袋', purpose: '冷萃咖啡液萃取 · 美国订单' },
    { id: 'i-2', name: '巴西日晒生咖啡豆', spec: '60kg / 袋', quantity: 18, unit: '袋', purpose: '闪萃咖啡浓缩液 · 新加坡订单' },
    { id: 'i-3', name: '250ml 氮气铝罐（含易拉盖）', spec: '50罐×20 / 箱', quantity: 8, unit: '箱', purpose: '冷萃液灌装 · 沙特订单' },
  ],
}

const seed = (): Claim[] => [
  claim012,
  {
    id: 'c-018',
    code: 'MO-20261102-018',
    title: '冻干咖啡产线包材申领',
    workshop: '冻干车间',
    workshopCode: 'FZ-02',
    applicant: '张伟',
    applicantTitle: '车间主管',
    phone: '138****6688',
    demandDate: '2026-10-30',
    urgency: 'urgent',
    remark: '冻干产线排产缺口，需在 10/30 前到厂。',
    status: 'approved',
    createdAt: '2026-11-02T14:10:00+08:00',
    updatedAt: '2026-11-02T16:40:00+08:00',
    submittedAt: '2026-11-02T14:12:00+08:00',
    approver: '李四',
    items: [
      { id: 'i-4', name: '冻干咖啡玻璃瓶 30g 装', spec: '60 瓶 / 箱', quantity: 12, unit: '箱', purpose: '冻干粉灌装' },
      { id: 'i-5', name: '品牌外包装彩盒', spec: '100 只 / 包', quantity: 6, unit: '包', purpose: '出口订单整箱包装' },
    ],
  },
  {
    id: 'c-005',
    code: 'MO-20261102-005',
    title: '灌装车间包材补货',
    workshop: '包装车间',
    workshopCode: 'BZ-01',
    applicant: '张伟',
    applicantTitle: '车间主管',
    phone: '138****6688',
    demandDate: '2026-11-04',
    urgency: 'urgent',
    remark: 'BIB 内袋库存不足 2 天产能，请优先安排。',
    status: 'rejected',
    createdAt: '2026-11-01T09:40:00+08:00',
    updatedAt: '2026-11-01T10:05:00+08:00',
    submittedAt: '2026-11-01T09:45:00+08:00',
    approver: '李四',
    items: [
      { id: 'i-6', name: '冷萃 BIB 内袋 10L', spec: '20 只 / 箱', quantity: 10, unit: '箱', purpose: '冷萃液大包装灌装' },
    ],
  },
  {
    id: 'c-022',
    code: 'MO-20261031-022',
    title: '新品中试原料申领（闪萃 · 燕麦风味）',
    workshop: '研发中试车间',
    workshopCode: 'YF-01',
    applicant: '张伟',
    applicantTitle: '车间主管',
    phone: '138****6688',
    demandDate: '2026-11-06',
    urgency: 'normal',
    remark: '配合燕麦风味闪萃新品打样，需中试原料与留样瓶。',
    status: 'approving',
    createdAt: '2026-10-31T13:50:00+08:00',
    updatedAt: '2026-10-31T14:22:00+08:00',
    submittedAt: '2026-10-31T14:22:00+08:00',
    approver: '李四',
    items: [
      { id: 'i-7', name: '燕麦风味糖浆（中试级）', spec: '5kg / 桶', quantity: 4, unit: '桶', purpose: '新品风味打样' },
      { id: 'i-8', name: '留样瓶 100ml', spec: '50 只 / 包', quantity: 8, unit: '包', purpose: '中试留样检测' },
    ],
  },
  {
    id: 'c-011',
    code: 'MO-20261029-011',
    title: '仓储耗材周度申领',
    workshop: '仓储部',
    workshopCode: 'WH-01',
    applicant: '张伟',
    applicantTitle: '车间主管',
    phone: '138****6688',
    demandDate: '2026-11-05',
    urgency: 'normal',
    remark: '',
    status: 'draft',
    createdAt: '2026-10-29T11:08:00+08:00',
    updatedAt: '2026-10-29T11:08:00+08:00',
    submittedAt: null,
    items: [
      { id: 'i-9', name: '出口木托盘（熏蒸合格）', spec: '1200×800mm', quantity: 40, unit: '个', purpose: '出口集装箱装柜' },
    ],
  },
  {
    id: 'c-003',
    code: 'MO-20261028-003',
    title: '车间清洁消毒耗材申领',
    workshop: '萃取车间',
    workshopCode: 'EX-01',
    applicant: '张伟',
    applicantTitle: '车间主管',
    phone: '138****6688',
    demandDate: '2026-10-31',
    urgency: 'normal',
    remark: '月度常规补货，用于产线 CIP 清洗与工器具消毒。',
    status: 'approved',
    createdAt: '2026-10-28T10:02:00+08:00',
    updatedAt: '2026-10-28T11:30:00+08:00',
    submittedAt: '2026-10-28T10:10:00+08:00',
    approver: '李四',
    items: [
      { id: 'i-10', name: '食品级管道清洗剂', spec: '5L / 桶', quantity: 6, unit: '桶', purpose: '萃取线 CIP 清洗' },
    ],
  },
]

let claims: Claim[] = seed()

const histories: Record<string, ApprovalRecord[]> = {
  'c-012': [
    {
      id: 'h-1',
      action: 'submit',
      operator: '张伟',
      operatorRole: 'submitter',
      comment: '附言：需求较急，麻烦尽快审批，周五前到货。',
      createdAt: '2026-11-03T09:12:00+08:00',
      fromStatus: 'draft',
      toStatus: 'submitted',
    },
    {
      id: 'h-2',
      action: 'ai_validate',
      operator: '系统 AI',
      operatorRole: 'system',
      comment: '字段完整，数量与单位匹配',
      createdAt: '2026-11-03T09:12:30+08:00',
      fromAgent: true,
    },
    {
      id: 'h-3',
      action: 'approve',
      operator: '李四',
      operatorRole: 'approver',
      comment: '已受理，等待库存确认后同意。',
      createdAt: '2026-11-03T10:30:00+08:00',
      fromStatus: 'submitted',
      toStatus: 'approving',
    },
  ],
  'c-018': [
    {
      id: 'h-4',
      action: 'submit',
      operator: '张伟',
      operatorRole: 'submitter',
      createdAt: '2026-11-02T14:12:00+08:00',
      fromStatus: 'draft',
      toStatus: 'submitted',
    },
    {
      id: 'h-5',
      action: 'approve',
      operator: '李四',
      operatorRole: 'approver',
      comment: '活动物料合理，同意。',
      createdAt: '2026-11-02T16:40:00+08:00',
      fromStatus: 'approving',
      toStatus: 'approved',
    },
  ],
  'c-005': [
    {
      id: 'h-6',
      action: 'submit',
      operator: '张伟',
      operatorRole: 'submitter',
      createdAt: '2026-11-01T09:45:00+08:00',
      fromStatus: 'draft',
      toStatus: 'submitted',
    },
    {
      id: 'h-7',
      action: 'reject',
      operator: '李四',
      operatorRole: 'approver',
      comment: '16oz 热饮杯上批已申领 10 箱，本周库存充足，请核对后再提交。',
      createdAt: '2026-11-01T10:05:00+08:00',
      fromStatus: 'approving',
      toStatus: 'rejected',
    },
  ],
  'c-022': [
    {
      id: 'h-8',
      action: 'submit',
      operator: '张伟',
      operatorRole: 'submitter',
      createdAt: '2026-10-31T14:22:00+08:00',
      fromStatus: 'draft',
      toStatus: 'submitted',
    },
  ],
  'c-011': [],
  'c-003': [
    {
      id: 'h-9',
      action: 'submit',
      operator: '张伟',
      operatorRole: 'submitter',
      createdAt: '2026-10-28T10:10:00+08:00',
      fromStatus: 'draft',
      toStatus: 'submitted',
    },
    {
      id: 'h-10',
      action: 'approve',
      operator: '李四',
      operatorRole: 'approver',
      createdAt: '2026-10-28T11:30:00+08:00',
      fromStatus: 'approving',
      toStatus: 'approved',
    },
  ],
}

const now = () => new Date().toISOString()

function nextCode() {
  const d = new Date()
  const stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`
  const seq = String(claims.length + 30).padStart(3, '0')
  return `MO-${stamp}-${seq}`
}

export const mock = {
  async login(payload: LoginPayload): Promise<LoginResult> {
    await delay(420)
    const user = USERS[payload.account.toUpperCase()] ?? {
      id: `u-${payload.account}`,
      account: payload.account,
      name: payload.role === 'approver' ? '林晓' : '张伟',
      role: payload.role,
      workshop: payload.role === 'approver' ? '城阳工厂' : '萃取车间',
      title: payload.role === 'approver' ? '生产经理' : '车间主管',
    }
    if (!payload.password) throw new Error('请输入密码')
    return { token: `mock-token-${Date.now()}`, user: { ...user, role: payload.role } }
  },

  async listMine(query: ClaimListQuery): Promise<PageResult<Claim>> {
    await delay()
    const keyword = query.keyword?.trim().toLowerCase()
    const filtered = claims.filter((c) => {
      if (query.status && query.status !== 'all' && c.status !== query.status) return false
      if (query.workshop && query.workshop !== 'all' && !c.workshop.includes(query.workshop)) return false
      if (keyword && !`${c.code}${c.title}`.toLowerCase().includes(keyword)) return false
      return true
    })
    const page = query.page ?? 1
    const pageSize = query.pageSize ?? 10
    return {
      list: filtered.slice((page - 1) * pageSize, page * pageSize),
      total: filtered.length,
      page,
      pageSize,
    }
  },

  async listPending(query: ClaimListQuery): Promise<PageResult<Claim>> {
    const res = await mock.listMine({ ...query, status: 'all' })
    const pending = res.list.filter((c) => c.status === 'submitted' || c.status === 'approving')
    return { ...res, list: pending, total: pending.length }
  },

  async get(id: string): Promise<Claim> {
    await delay(200)
    const found = claims.find((c) => c.id === id || c.code === id)
    if (!found) throw new Error('单据不存在')
    return found
  },

  async create(payload: Partial<Claim>): Promise<Claim> {
    await delay(380)
    const draft: Claim = {
      id: `c-${Date.now()}`,
      code: nextCode(),
      title: payload.title || '未命名申领单',
      workshop: payload.workshop || '萃取车间',
      workshopCode: payload.workshopCode || 'EX-01',
      applicant: payload.applicant || '张伟',
      applicantTitle: payload.applicantTitle || '车间主管',
      phone: payload.phone || '138****6688',
      demandDate: payload.demandDate || '',
      urgency: payload.urgency || 'normal',
      remark: payload.remark || '',
      status: 'draft',
      items: payload.items || [],
      createdAt: now(),
      updatedAt: now(),
      submittedAt: null,
    }
    claims = [draft, ...claims]
    histories[draft.id] = []
    return draft
  },

  async saveDraft(id: string, payload: Partial<Claim>): Promise<Claim> {
    await delay(320)
    const target = claims.find((c) => c.id === id)
    if (!target) throw new Error('单据不存在')
    if (target.status !== 'draft' && target.status !== 'rejected') {
      throw new Error('仅草稿或已驳回单据可以编辑')
    }
    Object.assign(target, payload, { updatedAt: now() })
    return target
  },

  async submit(id: string): Promise<Claim> {
    await delay(360)
    const target = claims.find((c) => c.id === id)
    if (!target) throw new Error('单据不存在')
    if (target.status !== 'draft' && target.status !== 'rejected') {
      throw new Error(`当前状态「${target.status}」不可提交，仅草稿或已驳回单据可提交`)
    }
    const from = target.status
    target.status = 'submitted'
    target.submittedAt = now()
    target.updatedAt = now()
    ;(histories[id] ||= []).push({
      id: `h-${Date.now()}`,
      action: 'submit',
      operator: target.applicant,
      operatorRole: 'submitter',
      createdAt: now(),
      fromStatus: from,
      toStatus: 'submitted',
    })
    return target
  },

  async withdraw(id: string): Promise<Claim> {
    await delay(300)
    const target = claims.find((c) => c.id === id)
    if (!target) throw new Error('单据不存在')
    if (!['submitted', 'approving'].includes(target.status)) {
      throw new Error('仅已提交 / 审批中的单据可以撤销')
    }
    const from = target.status
    target.status = 'draft'
    target.submittedAt = null
    target.updatedAt = now()
    ;(histories[id] ||= []).push({
      id: `h-${Date.now()}`,
      action: 'withdraw',
      operator: target.applicant,
      operatorRole: 'submitter',
      comment: '提交人撤销提交',
      createdAt: now(),
      fromStatus: from,
      toStatus: 'draft',
    })
    return target
  },

  async approve(id: string, comment?: string): Promise<Claim> {
    await delay(340)
    const target = claims.find((c) => c.id === id)
    if (!target) throw new Error('单据不存在')
    if (!['submitted', 'approving'].includes(target.status)) {
      throw new Error('当前状态不可审批')
    }
    const from = target.status
    target.status = 'approved'
    target.updatedAt = now()
    ;(histories[id] ||= []).push({
      id: `h-${Date.now()}`,
      action: 'approve',
      operator: '林晓',
      operatorRole: 'approver',
      comment: comment || '同意',
      createdAt: now(),
      fromStatus: from,
      toStatus: 'approved',
    })
    return target
  },

  async reject(id: string, comment: string): Promise<Claim> {
    await delay(340)
    if (!comment?.trim()) throw new Error('驳回必须填写驳回意见')
    const target = claims.find((c) => c.id === id)
    if (!target) throw new Error('单据不存在')
    if (!['submitted', 'approving'].includes(target.status)) {
      throw new Error('当前状态不可驳回')
    }
    const from = target.status
    target.status = 'rejected'
    target.updatedAt = now()
    ;(histories[id] ||= []).push({
      id: `h-${Date.now()}`,
      action: 'reject',
      operator: '林晓',
      operatorRole: 'approver',
      comment,
      createdAt: now(),
      fromStatus: from,
      toStatus: 'rejected',
    })
    return target
  },

  async history(id: string): Promise<ApprovalRecord[]> {
    await delay(180)
    return histories[id] ?? []
  },

  async summary(claim: Partial<Claim>): Promise<ClaimSummary> {
    await delay(900)
    const count = claim.items?.length ?? 0
    const names = (claim.items ?? []).map((i) => i.name).join(' / ')
    return {
      summary: `${claim.title || '未命名申领单'} · ${count} 类货品${names ? `（${names}）` : ''} · 优先级：${
        claim.urgency === 'urgent' ? '加急' : '普通'
      } · 期望 ${claim.demandDate || '未填写'} 前到货`,
      highlights: [
        `申领车间：${claim.workshop || '未填写'}`,
        `明细共 ${count} 行，合计 ${(claim.items ?? []).reduce((s, i) => s + (i.quantity || 0), 0)} 件`,
        claim.urgency === 'urgent' ? '标记为加急，需优先安排产线备料' : '普通优先级，按常规排产节奏备料',
      ],
    }
  },

  async validate(claim: Partial<Claim>): Promise<ClaimValidation> {
    await delay(1100)
    const missing: string[] = []
    if (!claim.title?.trim()) missing.push('单据标题')
    if (!claim.workshop?.trim()) missing.push('申领车间')
    if (!claim.demandDate) missing.push('需求日期')
    if (!claim.items?.length) missing.push('货品明细')
    const issues: string[] = []
    if (!claim.remark?.trim()) issues.push('建议补充「备注说明」，便于仓库安排配送')
    const badRow = (claim.items ?? []).find((i) => !i.quantity || i.quantity <= 0)
    if (badRow) issues.push(`明细「${badRow.name}」数量需大于 0`)

    return {
      passed: missing.length === 0 && issues.length === 0,
      message: missing.length
        ? `缺少 ${missing.length} 个必填字段：${missing.join('、')}`
        : issues.length
          ? '字段已填写完整，存在优化建议'
          : '校验通过 · 字段完整',
      issues,
      missingFields: missing,
    }
  },

  async chatStream(
    payload: { claimId?: string; question: string },
    onDelta: (chunk: string) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    const answer = payload.question.includes('库存')
      ? '按昨日库存快照：埃塞俄比亚水洗生豆可用 96 袋（安全库存 60 袋），巴西日晒生豆可用 85 袋（安全库存 50 袋），250ml 氮气铝罐可用 30 箱（安全库存 15 箱）。本次申领数量均在可用范围内，可正常审批。'
      : payload.question.includes('备注')
        ? '建议备注：本单对应美国客户订单 PO-2611-03 的冷萃液产线备料，已核对上周产线消耗量；生豆为萃取刚需，铝罐用于灌装线。请仓库于 11/07 前送达车间，到货后由车间领班验收并录入批次号。'
        : payload.question.includes('合规') || payload.question.includes('校验')
          ? '校验结果：3 行明细的品名、规格、数量均完整，单位与规格匹配；需求日期晚于提交日期，符合规则。建议补充「关联客户订单号」，便于仓库按出口订单优先备货。'
          : '该单据为城阳工厂萃取车间 11 月出口订单备料：3 类物料（生咖啡豆 42 袋、氮气铝罐 8 箱），需求日期 11-08；提交人张伟，审批人李四。涉及美国、新加坡、沙特三个出口订单，建议生豆先进厂待检，按批次投产。'

    const chunks = answer.match(/[\s\S]{1,3}/g) ?? []
    for (const piece of chunks) {
      if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
      await delay(28)
      onDelta(piece)
    }
  },
}
