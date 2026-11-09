import { useEffect, useRef, useState } from 'react';
import { ssePost } from '@/api/sse';

/**
 * 侧边 Agent 对话面板：
 *  - 支持 SSE 流式打字机输出
 *  - 消息区分 user / assistant
 */

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
}

interface AgentChatProps {
  /** 触发对话的上下文，比如单据 ID */
  contextId?: string;
}

export default function AgentChat({ contextId }: AgentChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<(() => void) | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 自动滚到底部
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  const send = () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: text,
    };
    const assistantId = `a-${Date.now()}`;
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      streaming: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput('');
    setLoading(true);

    // 调用 SSE 流式接口（路径可按后端实际调整）
    abortRef.current = ssePost(
      '/agent/chat/stream',
      { message: text, context_id: contextId },
      {
        onMessage: (chunk) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: m.content + chunk } : m,
            ),
          );
        },
        onDone: () => {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, streaming: false } : m)),
          );
          setLoading(false);
        },
        onError: (err) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content || `⚠️ 对话失败：${err.message}`, streaming: false }
                : m,
            ),
          );
          setLoading(false);
        },
      },
    );
  };

  const stop = () => {
    abortRef.current?.();
    setMessages((prev) =>
      prev.map((m) => (m.streaming ? { ...m, streaming: false } : m)),
    );
    setLoading(false);
  };

  return (
    <div className="flex h-full flex-col">
      {/* 消息区 */}
      <div
        ref={scrollRef}
        className="flex-1 space-y-3 overflow-y-auto px-4 py-3"
      >
        {messages.length === 0 && (
          <div className="mt-4 text-center text-sm text-slate-400">
            您好，我是企业审批助手，有任何关于单据或流程的问题都可以问我 👋
          </div>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm leading-relaxed ${
                m.role === 'user'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-100 text-slate-800'
              } ${m.streaming ? 'typing-cursor' : ''}`}
            >
              {m.content || (m.streaming ? '' : '（空回复）')}
            </div>
          </div>
        ))}
      </div>

      {/* 输入区 */}
      <div className="border-t border-slate-200 p-3">
        <div className="flex items-end gap-2">
          <textarea
            className="textarea flex-1"
            rows={2}
            placeholder="请输入您的问题，回车发送…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            disabled={loading}
          />
          {loading ? (
            <button className="btn-outline" onClick={stop}>
              停止
            </button>
          ) : (
            <button className="btn-primary" onClick={send}>
              发送
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
