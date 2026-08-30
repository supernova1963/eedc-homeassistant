import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Backend↔Client-Spiegel-Gate (2026-08-30): Zwei Vokabulare stehen im Repo
// zweimal — die Themenschalter des Monatsberichts (Python-Builder ↔
// DokumentationsDialog) und die Energie-Kategorien der Monatsauswertung
// (energie_profil/views.py ↔ lib/colors.ts). Verbunden waren sie bis dahin nur
// durch einen Kommentar; keiner der übrigen check:* schaut über die
// Sprachgrenze. Drift hieß: ein Schalter, der still nichts tut, oder ein Thema,
// das niemand wählen kann — in beiden Richtungen ohne Fehlermeldung.
const FRONTEND_ROOT = process.cwd()

describe('Backend↔Client-Spiegel (THEMEN · ENERGIE_KATEGORIE)', () => {
  it('beide Seiten führen dieselben Schlüssel und Labels', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-spiegel-backend.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
