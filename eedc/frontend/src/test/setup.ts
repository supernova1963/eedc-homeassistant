// Vitest-Setup: jest-dom-Matcher (toBeInTheDocument etc.) registrieren +
// nach jedem Test das DOM aufräumen. Wird via vitest.config.ts geladen.
import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// recharts' ResponsiveContainer nutzt ResizeObserver — in jsdom nicht vorhanden.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
}

// Formulare springen bei Validierungsfehlern zum ersten Feld — jsdom kennt
// scrollIntoView nicht und wirft sonst eine unhandled rejection.
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}

afterEach(() => {
  cleanup()
})
