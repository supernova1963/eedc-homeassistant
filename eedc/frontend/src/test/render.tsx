/**
 * Render-Helfer für die Frontend-Tests (Etappe E5 / M8).
 *
 * **Warum es sie gibt.** Sieben v4-Testdateien bauten wortgleich denselben
 * Provider-Turm `MemoryRouter → ThemeProvider → Komponente`, und elf Dateien
 * trugen denselben `matchMedia`-Stub in vierzehn byte-identischen Kopien
 * (gemessen 2026-08-24). Beides ist Aufbau, keine Aussage — es gehört an eine
 * Stelle, damit eine Änderung am Aufbau nicht vierzehnmal nachgezogen werden
 * muss.
 *
 * ⚠ **`stubMatchMedia` steht bewusst NICHT in `setup.ts`.** Ein globaler Stub
 * gäbe ihn auch den 147 Testdateien, die heute ohne `window.matchMedia` laufen —
 * eine Komponente, die per Feature-Test auf sein Fehlen reagiert, würde still
 * anders rendern. Wer ihn braucht, ruft ihn.
 */
import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import { ThemeProvider } from '../context/ThemeContext'

/**
 * Rendert in `MemoryRouter → ThemeProvider`. `route` setzt den Einstiegspfad,
 * wo die Sicht ihn über `useSearchParams`/`useLocation` liest; ohne Angabe
 * bleibt der Router auf seinem Default (`/`) — genau wie die Bestandsaufrufe
 * ohne `initialEntries`.
 */
export function renderMitProvidern(ui: ReactElement, opt: { route?: string } = {}) {
  return render(
    <MemoryRouter {...(opt.route ? { initialEntries: [opt.route] } : {})}>
      <ThemeProvider>{ui}</ThemeProvider>
    </MemoryRouter>,
  )
}

/**
 * `ThemeProvider`/`useChartTheme` fragen `prefers-color-scheme` ab; jsdom kennt
 * `matchMedia` nicht und wirft sonst. `matches: false` = helles Theme — dieselbe
 * Antwort, die alle vierzehn Bestandskopien gaben.
 */
export function stubMatchMedia() {
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
    matches: false, media: '', onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  }))
}
