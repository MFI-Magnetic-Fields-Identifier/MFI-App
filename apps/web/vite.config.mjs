import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '^/predict$': process.env.MFI_API_TARGET || 'http://127.0.0.1:8000',
      '^/motors(?:/.*)?$': process.env.MFI_API_TARGET || 'http://127.0.0.1:8000',
      '^/health$': process.env.MFI_API_TARGET || 'http://127.0.0.1:8000',
    },
  },
})
