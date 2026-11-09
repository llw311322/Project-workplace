import { useEffect, useRef, useState } from 'react'
import { Bot, Send, Sparkles, Square } from 'lucide-react'
import { agentApi } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { Claim } from '@/lib/types'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  degraded?: boolean
  thinking?: boolean
}

const QUICK_ACTIONS = [
  { label: '生成单据摘要', question: '帮我总结这张单据的要点' },
  { label: '检查字段合规', question: '检查这张单据的字段是否合规' },
  { label: '查询库存', question: '查一下本次申领货品的当前库存' },
  { label: '生成备注', question: '帮我生成一条审批备注' },
]

const WELCOME =
  '已加载当前单据。你可以问我单据要点、库存情况，或让我生成审批备注。'

/**
 * ReAct 中间输出过滤。
 * LangChain Agent 的原始流里混着 Thought / Action / Observation 推理过程，
 * 最终答案以 "Final Answer:" 开头。这里把推理阶段渲染为"思考中…"，
 * 答案阶段只保留 Final Answer 之后的正文。
 */
const FINAL_MARK = 'Final Answer:'

function renderAgentOutput(raw: string): { text: string; thinking: boolean } {
  const idx = raw.lastIndexOf(FINAL_MARK)
  if (idx !== -1) {
    const text = raw.slice(idx + FINAL_MARK.length).replace(/^\s+/, '')
    return { text: text || '…', thinking: false }
  }
  // 还在推理阶段（或模型直接作答）：包含推理标记就不把中间过程亮出来
  if (/(Thought:|Action:|Action Input:|Observation:)/.test(raw)) {
    return { text: '', thinking: true }
  }
  return { text: raw, thinking: false }
}

export function AgentPanel({ claim }: { claim: Claim | null }) {
  const [messages, setMessages] = useState<Message[]>([
    { id: 'welcome', role: 'assistant', content: WELCOME },
  ])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // 切换单据时重置会话
  useEffect(() => {
    setMessages([{ id: 'welcome', role: 'assistant', content: WELCOME }])
  }, [claim?.id])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages])

  const send = async (question?: string) => {
    const q = (question ?? input).trim()
    if (!q || streaming) return

    const aiId = `ai-${Date.now()}`
    setMessages((m) => [...m, { id: `u-${Date.now()}`, role: 'user', content: q }])
    setInput('')
    setStreaming(true)

    const controller = new AbortController()
    abortRef.current = controller
    setMessages((m) => [...m, { id: aiId, role: 'assistant', content: '', streaming: true }])

    const patchAi = (patch: Partial<Message>) =>
      setMessages((m) => m.map((msg) => (msg.id === aiId ? { ...msg, ...patch } : msg)))

    let acc = ''
    try {
      await agentApi.chatStream(
        { claimId: claim?.id, question: q },
        {
          onDelta: (chunk) => {
            acc += chunk
            // 过滤 ReAct 推理中间输出，只把最终答案渲染给用户
            const r = renderAgentOutput(acc)
            patchAi({ content: r.text, thinking: r.thinking })
          },
          signal: controller.signal,
        },
      )
      const final = renderAgentOutput(acc)
      patchAi({ content: final.text, thinking: final.thinking, streaming: false })
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        patchAi({ streaming: false, content: '（已停止生成）' })
      } else {
        // Agent 降级：不阻断业务，仅提示
        patchAi({
          streaming: false,
          degraded: true,
          content:
            'AI 助手暂时不可用（LLM 超时或接口异常）。单据的保存与审批流程不受影响，可稍后重试或直接联系审批人处理。',
        })
      }
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }

  return (
    <aside className="flex h-[46vh] w-full shrink-0 flex-col border-t border-line bg-white lg:h-full lg:w-[360px] lg:border-l lg:border-t-0">
      {/* 面板头 */}
      <div className="flex h-[60px] shrink-0 items-center gap-2.5 border-b border-line px-4">
        <span className="flex h-[30px] w-[30px] items-center justify-center rounded-full bg-primary">
          <Sparkles className="h-4 w-4 text-white" />
        </span>
        <div>
          <p className="text-sm font-medium text-ink">AI 助手 · 单据对话</p>
          <p className="flex items-center gap-1.5 text-[11px] text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-[#22C55E]" />
            在线 · 已挂载知识库（RAG）
          </p>
        </div>
      </div>

      {/* 消息区 */}
      <div ref={scrollRef} className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
        {messages.map((msg) =>
          msg.role === 'user' ? (
            <div key={msg.id} className="flex justify-end">
              <div className="max-w-[80%] rounded-xl bg-primary px-3 py-2.5 text-[13px] leading-5 text-white">
                {msg.content}
              </div>
            </div>
          ) : (
            <div key={msg.id} className="flex items-start gap-2">
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary">
                <Bot className="h-3.5 w-3.5 text-white" />
              </span>
              <div
                className={cn(
                  'min-w-0 max-w-[85%] rounded-xl px-3 py-2.5 text-[13px] leading-5',
                  msg.degraded ? 'bg-[#FEF3C7] text-[#92400E]' : 'bg-[#F3F4F6] text-ink-2',
                )}
              >
                {msg.content || (msg.streaming ? '思考中…' : '…')}
                {msg.streaming && <span className="stream-caret" />}
              </div>
            </div>
          ),
        )}
      </div>

      {/* 快捷能力 */}
      <div className="flex flex-wrap gap-2 px-4 pb-2">
        {QUICK_ACTIONS.map((a) => (
          <button
            key={a.label}
            type="button"
            disabled={streaming}
            onClick={() => send(a.question)}
            className="rounded-full bg-primary-light px-2.5 py-1 text-xs text-primary transition-colors hover:bg-[#E3E6FD] disabled:opacity-50"
          >
            {a.label}
          </button>
        ))}
      </div>

      {/* 输入区 */}
      <div className="flex shrink-0 items-center gap-2 border-t border-line p-3">
        <input
          className="h-10 w-full rounded-lg bg-[#F3F4F6] px-3 text-[13px] outline-none placeholder:text-faint focus:bg-white focus:ring-2 focus:ring-primary/20"
          placeholder="输入问题，Enter 发送"
          value={input}
          disabled={streaming}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.nativeEvent.isComposing) send()
          }}
        />
        {streaming ? (
          <button
            type="button"
            title="停止生成"
            onClick={() => abortRef.current?.abort()}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#6B7280] text-white hover:bg-[#4B5563]"
          >
            <Square className="h-4 w-4" />
          </button>
        ) : (
          <button
            type="button"
            title="发送"
            onClick={() => send()}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary text-white hover:bg-primary-hover"
          >
            <Send className="h-[18px] w-[18px]" />
          </button>
        )}
      </div>

      <div className="border-t border-line bg-field px-3 py-2 text-center text-[11px] text-faint">
        LLM 超时 / 异常时自动降级，单据保存与审批不受影响
      </div>
    </aside>
  )
}
