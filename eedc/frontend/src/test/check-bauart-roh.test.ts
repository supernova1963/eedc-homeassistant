import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Client-Hälfte von ADR-002/**P13** (05.09.2026): Die Bauart einer Wärmepumpe
// (`wp_art`) entscheidet nicht, welche Größe gemessen, gefordert oder gezeigt
// wird — das sagt der zugeordnete Zähler (SOLL Wärme/Klima §3.2a, R1). Jede
// Datei, die die Bauart liest, steht klassifiziert in `scripts/check-bauart-roh.mjs`.
//
// Anlass: sechs neue Bauart-Leser in 16 Tagen; einer davon (`b9807ac4`, 03.09.)
// entschied die Warmwasser-Achse nach Bauart und wurde zwei Tage später auf
// Beleglage umgebaut (#404) — weil der Maintainer fragte, nicht weil ein Test
// rot war. Der Wrapper ist Pflicht (M14).
const FRONTEND_ROOT = process.cwd()

describe('Bauart entscheidet keine Größe (ADR-002/P13, R1)', () => {
  it('jede Client-Datei, die wp_art liest, ist klassifiziert', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-bauart-roh.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
