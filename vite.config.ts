import path from 'node:path'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 5173,
      // server/ 是 Python 后端代码，前端不需要监听（否则复制/写入时会 EBUSY 崩掉）
      watch: {
        ignored: ['**/server/**', '**/.workbuddy/**'],
      },
      proxy: {
        // FastAPI 后端；SSE 需要关闭缓冲，保持默认即可
        '/api': {
          target,
          changeOrigin: true,
        },
      },
    },
  }
})
