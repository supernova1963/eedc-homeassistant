import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Client-Hälfte der Wirtschaftlichkeitsrechnung (N-132, gebaut mit N-230):
// die Amortisations**dauer** hat einen Backend-SoT
// (`core/berechnungen/kapitalrechnung.py`) mit zwei Hälften, die nur gemeinsam
// stimmen — Kapitaleinsatz als Nenner, annualisierte Ersparnis als Zähler.
// Der Client zeigt sie an; er bildet sie nicht.
//
// Warum es diesen Wächter gibt: Der Wallbox-Hub rechnete
// `Anschaffung ÷ Ersparnis` und ließ damit Alternativkosten, Förderung und
// Betriebskosten weg — eine geförderte Wallbox bekam eine zu lange Dauer,
// direkt neben der Zahl des ROI-Dashboards. Von den damals 28 `check:*`
// hatte keiner die Finanzzeile.
const FRONTEND_ROOT = process.cwd()

describe('Amortisationsdauer nur aus dem Backend (Konzept §5/§8-6)', () => {
  it('kein Client-Code bildet eine Dauer in Jahren selbst', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-finanz-roh.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
