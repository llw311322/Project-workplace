import { BASE_URL } from './request';
import { getToken } from '@/utils/storage';

/**
 * SSE 流式接收工具（用 fetch + ReadableStream 实现）
 *
 * 为什么不用 EventSource？
 *  - EventSource 只支持 GET，不能带 POST body
 *  - EventSource 不支持自定义 header（需要 Authorization）
 *
 * 协议假设（与后端约定）：
 *  - 后端返回 text/event-stream
 *  - 每个事件以 \n\n 结尾，单条事件内部可能有多行 data: ...
 *
 * @param url  相对路径（如 /agent/chat/stream）
 * @param payload 请求 body（JSON）
 * @param handlers.onMessage  每条 SSE 消息（data 内容）
 * @param handlers.onDone     流结束
 * @param handlers.onError    错误
 * @returns abort 函数，可中途取消
 */
export function ssePost(
  url: string,
  payload: Record<string, unknown>,
  handlers: {
    onMessage: (chunk: string) => void;
    onDone?: () => void;
    onError?: (err: Error) => void;
  },
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const token = getToken();
      const resp = await fetch(`${BASE_URL}${url}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (!resp.ok || !resp.body) {
        throw new Error(`SSE 请求失败：${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // 按 \n\n 切帧：每帧是一个 SSE 事件
        let idx: number;
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const rawEvent = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);

          // 只提取 "data:" 行的内容，合并成一条字符串
          const dataLines = rawEvent
            .split('\n')
            .filter((line) => line.startsWith('data:'))
            .map((line) => line.slice(5).replace(/^\s/, ''));

          const dataStr = dataLines.join('\n').trim();
          if (!dataStr) continue;

          // 心跳 / 结束事件：后端约定 data: [DONE]
          if (dataStr === '[DONE]') {
            handlers.onDone?.();
            return;
          }

          handlers.onMessage(dataStr);
        }
      }

      handlers.onDone?.();
    } catch (err) {
      if ((err as Error).name === 'AbortError') return; // 用户主动取消
      handlers.onError?.(err as Error);
    }
  })();

  return () => controller.abort();
}
