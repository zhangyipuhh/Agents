import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
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
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8003',
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
})
