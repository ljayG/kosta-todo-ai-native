import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // 개발 중에는 /api 요청을 로컬 FastAPI로 넘긴다 (VITE_API_BASE_URL을 비워 둔 경우)
    proxy: {
      '/api': process.env.API_PROXY_TARGET || 'http://localhost:8000',
    },
  },
})
