import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// W2 — Client-Hälfte der Ergebnis-Leiter (Paket „Ergebnisgrößen Monat/Jahr in den Layer", 03.10.2026):
// Netto-Ertrag, Monats-/Jahresergebnis, SOLL-Erfüllung, Jahresquoten und die Jahresfaltung entstehen im
// Backend-Layer (`core/berechnungen/ergebnis.py`); Cockpit Monat/Jahr und Finanzen LESEN sie. Die Backend-Hälfte
// hält `backend/tests/test_ergebnis_leiter_nur_im_layer.py` (W1). Gegenprobe beim Bau: gegen den Stand v4.1.1
// meldet der Prüfer 23 Rechnungen (u. a. das Monatsergebnis in MonatBilanz/JahrBilanz, die SOLL-Quote, die
// ganze Jahresfaltung) — heute 0, mit acht klassifizierten Ausnahmen.
const FRONTEND_ROOT = process.cwd()

describe('Ergebnisgrößen nur aus dem Backend (W2)', () => {
  it('Cockpit Monat/Jahr und Finanzen rechnen nicht mit Antwortwerten', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-ergebnis-roh.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
