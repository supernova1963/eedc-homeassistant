import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Client-Hälfte von ADR-002/**P12** (02.09.2026): Eine Arbeitszahl entsteht
// ausschließlich in `core/berechnungen/waermepumpe_kennzahl.py::arbeitszahl`.
// Sie ist die einzige Kennzahl in eedc, die **nicht erscheinen darf**, wenn
// Zähler und Nenner verschieden abgegrenzt sind (SOLL §1/§4.2/§5) — eine rohe
// Division kann davon nichts wissen.
//
// Am 02.09.2026 rechneten acht Wege eine Arbeitszahl, **fünf davon an der Regel
// vorbei**: Werte-Tabelle, HA-Sensor „COP Durchschnitt", Jahresbericht-PDF,
// Monats-/Saisonvergleich und der Effizienz-Trend der Aussichten. Drei davon
// hat erst dieser Wächter gefunden — eine Namenssuche nach „cop"/„jaz" sah sie
// nicht, weil sie ihre Größen anders benennen.
//
// Der Wrapper ist Pflicht (M14): Ein Prüfer, der nur in package.json steht,
// läuft nirgends automatisch und ist eine Gedächtnisstütze, kein Wächter.
const FRONTEND_ROOT = process.cwd()

describe('Arbeitszahl nur aus dem Layer (ADR-002/P12)', () => {
  it('kein Client-Code dividiert eine Wärme- durch eine Stromgröße', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-cop-roh.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
