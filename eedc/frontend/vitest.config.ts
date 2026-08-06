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
    // Die Uhr gehört zur Hermetik (F-5). Ohne feste Zone hängt jeder Test, der
    // ein lokales Datum bildet, an der Einstellung der Maschine: auf diesem
    // Rechner läuft die Suite in CEST, der CI-Runner in UTC — dieselben
    // Zeilen fielen dort rot, ohne dass sich am Code etwas geändert hätte.
    // Gemessen beim Bau von F-5: drei Belege in `lib/datum.test.ts` kippen
    // zwischen den beiden Zonen. Europe/Berlin, weil eedc dieselbe Zone als
    // Anwendungs-Default führt (`docker-compose.yml`, `ZoneInfo` im Backend).
    env: { TZ: 'Europe/Berlin' },
  },
})
