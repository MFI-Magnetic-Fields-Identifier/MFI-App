import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const apiTarget = process.env.MFI_API_TARGET || 'https://mfi-a5su.onrender.com'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '^/predict$': apiTarget,
      '^/motors(?:/.*)?$': apiTarget,
      '^/health$': apiTarget,
    },
  },
})
