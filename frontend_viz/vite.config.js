import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    open: true
  },
  build: {
    // 编译到 dist 目录，供 FastAPI 直接挂载
    outDir: 'dist',
    emptyOutDir: true
  }
})