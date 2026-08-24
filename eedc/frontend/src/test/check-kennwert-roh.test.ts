import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Client-Haelfte von ADR-002/P3-a (A26/N106): ANZEIGE und RECHNUNG lesen
// `leistung_kwp_effektiv`, FORMULARE und WIZARDS die Rohspalte `leistung_kwp`.
// Der Backend-Waechter endet an der API-Grenze — das ist Grenze (c) der
// P3-a-Zeile in ADR-002, und dieses Skript schliesst sie.
//
// Warum dieser Wrapper (M14, Etappe E8, 2026-08-24): wie `check:roh-controls`
// daneben lief er als EIGENER CI-Schritt und in keinem Vitest-Lauf. Gerade bei
// diesem Pruefer wiegt das schwer — die Gegenseite der Regel (#229, Nennleistung
// nur im `parameter`-JSON) zeigt sich beim Nutzer als stille 0, nicht als
// Absturz. Sein CI-Schritt entfaellt mit diesem Wrapper.
const FRONTEND_ROOT = process.cwd()

describe('Investitions-kWp nur effektiv anzeigen (ADR-002/P3-a, Client)', () => {
  it('kein roher Kennwert-Zugriff ausserhalb der Eingabe', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-kennwert-roh.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
