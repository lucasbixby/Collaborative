import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// In dev, the API and the socket are proxied to the server on :8000, so the app calls its own
// origin as it does when FastAPI serves it (#22), and there's no CORS to set up.
const server = 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': server,
      '/health': server,
      '/ws': { target: server, ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['src/test/setup.ts'],
    restoreMocks: true,
    unstubGlobals: true,
  },
})
