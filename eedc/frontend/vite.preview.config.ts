import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

/**
 * Separater Build NUR für die öffentliche IA-v4-Vorschau (Wegwerf, Etappe 2).
 *
 * Eigener Entry (`preview.html` → `preview-main.tsx` mountet `<IASkeleton/>`
 * ohne DEV-Guard), eigenes Out-Dir (`preview-dist/`, gitignored) und die
 * GitHub-Pages-Base `/eedc-homeassistant/preview/`. Greift NICHT in den
 * Produktiv-Build (`vite.config.ts`, `base: './'`, `outDir: dist`) ein —
 * `npm run build` bleibt dadurch unverändert.
 *
 * `npm run build:preview` baut hierüber und benennt `preview.html` →
 * `index.html` um, damit der Pages-Pfad `…/preview/` sauber auflöst.
 */
export default defineConfig({
  plugins: [react()],
  base: '/eedc-homeassistant/preview/',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  // Die Vorschau referenziert keine public/-Assets (backgrounds/help/…) — nicht
  // mitkopieren, hält das Pages-Output schlank.
  publicDir: false,
  build: {
    outDir: 'preview-dist',
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      input: path.resolve(__dirname, 'preview.html'),
    },
  },
})
