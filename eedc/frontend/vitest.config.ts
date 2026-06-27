import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

// Frontend-Test-Infra (E1-P3, eng fokussiert — KEIN Coverage-Ziel).
// Zielscheiben: Routing/Redirects + KPICard (+ später <WerteTabelle>).
// Bewusst getrennt von vite.config.ts, damit der Produktions-Build-Pfad
// (tsc && vite build) unberührt bleibt.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    css: false,
  },
})
