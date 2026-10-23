import { realpathSync } from 'node:fs'
import path from 'node:path'
import { defineConfig, searchForWorkspaceRoot } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],

  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },

  server: {
    // 多工作树共享 node_modules 时，允许读取软链接实际指向的字体文件。
    fs: {
      allow: [
        searchForWorkspaceRoot(import.meta.dirname),
        realpathSync(path.resolve(import.meta.dirname, 'node_modules')),
      ],
    },
    proxy: {
      // 本地开发与生产环境统一使用 /api/*，不再维护旧的无前缀接口。
      '/api': {
        target: process.env.POETICUS_API_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
