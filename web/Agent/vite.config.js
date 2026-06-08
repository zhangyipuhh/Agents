import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

// https://vitejs.dev/config/
const __dirname = dirname(fileURLToPath(import.meta.url))

export default defineConfig(({ mode }) => {
  // 加载环境变量，从项目根目录加载（向上两级到 feature-agent-core 目录）
  const env = loadEnv(mode, resolve(__dirname, '../../'), '')

  return {
    plugins: [vue()],
    optimizeDeps: {
      include: [
        '@vue-office/docx',
        '@vue-office/excel',
        '@vue-office/pdf',
        'vue-demi',
      ],
    },
    build: {
      rollupOptions: {
        input: {
          main: resolve(__dirname, 'index.html'),
          knowledge: resolve(__dirname, 'knowledge.html'),
          portal: resolve(__dirname, 'portal.html'),
          login: resolve(__dirname, 'login.html'),
        },
      },
    },
    server: {
      host: true,
      proxy: {
        '/api': {
          target: env.VITE_API_TARGET || 'http://localhost:8001',
          changeOrigin: true,
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq, req) => {
              if (req.url?.includes('/chat')) {
                proxyReq.setHeader('Connection', 'keep-alive')
                proxyReq.setHeader('Cache-Control', 'no-cache')
                proxyReq.setHeader('Accept', 'text/event-stream')
              }
            })
            proxy.on('proxyRes', (proxyRes, req) => {
              if (req.url?.includes('/chat')) {
                delete proxyRes.headers['content-length']
                proxyRes.headers['cache-control'] = 'no-cache'
                proxyRes.headers['connection'] = 'keep-alive'
                proxyRes.headers['x-accel-buffering'] = 'no'
              }
            })
          }
        }
      }
    }
  }
})
