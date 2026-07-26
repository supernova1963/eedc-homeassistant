/**
 * Wächter: keine Identitätsfarbe in der PV-Modul-Palette (A20/N49).
 *
 * Der Komponenten-Hub-PV-Verlauf legt in EINEN Stapel: je Modul eine Farbe aus
 * {@link PV_MODUL_FARBEN} plus die Zusatz-Erzeuger mit ihrer **Identitätsfarbe**
 * (BKW, sonstige Erzeuger), daneben die drei Verwendungs-Serien. `PV_MODUL_FARBEN[3]`
 * war exakt der BKW-Identitätston (Amber-400). Ab dem vierten Modul waren zwei
 * Reihen desselben Charts nicht unterscheidbar; getroffen hat es genau
 * „mehrere Dachsegmente + Balkonkraftwerk".
 *
 * Der Wächter prüft auf **exakte Gleichheit**, nicht auf Ähnlichkeit: ein
 * Ähnlichkeits-Schwellwert wäre Geschmackssache und würde bestehende, bewusst
 * nahe Paare (Amber-300 gegen die BKW-Identität, ΔE ≈ 13) als Fehler melden.
 */
import { describe, it, expect } from 'vitest'
import {
  CHART_COLORS,
  KOMPONENTEN_FARBEN,
  PV_MODUL_BG,
  PV_MODUL_FARBEN,
  SONSTIGES_ERZEUGER_FARBE,
} from '../lib/colors'

/** Farben, die im selben Chart wie die Modul-Palette liegen (komponentenAdapter
 *  `pvVerlauf`: ERZ_ZUSATZ + die drei Verwendungs-Serien). */
const IM_SELBEN_CHART: Record<string, string> = {
  bkw: KOMPONENTEN_FARBEN['balkonkraftwerk'].hex,
  sonstigeErzeuger: SONSTIGES_ERZEUGER_FARBE.hex,
  direktverbrauch: CHART_COLORS.eigenverbrauch,
  speicherLadung: CHART_COLORS.speicherLadung,
  einspeisung: CHART_COLORS.einspeisung,
}

const IM_SELBEN_CHART_BG: Record<string, string> = {
  bkw: KOMPONENTEN_FARBEN['balkonkraftwerk'].bg,
  sonstigeErzeuger: SONSTIGES_ERZEUGER_FARBE.bg,
}

describe('PV-Modul-Palette kollidiert mit keiner Identitätsfarbe', () => {
  it.each(Object.entries(IM_SELBEN_CHART))(
    'kein Palettenton ist identisch mit %s',
    (rolle, hex) => {
      const treffer = PV_MODUL_FARBEN.map((f, i) => [i, f] as const).filter(
        ([, f]) => f.toLowerCase() === hex.toLowerCase(),
      )
      expect(
        treffer,
        `PV_MODUL_FARBEN[${treffer.map(([i]) => i).join(',')}] == ${hex} (${rolle}) — ` +
          `im Komponenten-Hub-PV-Verlauf liegen beide im selben Stapel und wären ` +
          `nicht unterscheidbar. Anderen Amber-Ton wählen und die ganze Palette ` +
          `gegen IM_SELBEN_CHART gegenprüfen, nicht nur den einen tauschen.`,
      ).toEqual([])
    },
  )

  it.each(Object.entries(IM_SELBEN_CHART_BG))(
    'keine Palettenklasse ist identisch mit %s (VerteilungsBalken)',
    (rolle, bg) => {
      expect(PV_MODUL_BG.filter((c) => c === bg), `${rolle}: ${bg}`).toEqual([])
    },
  )

  it('die Palette ist in sich duplikatfrei', () => {
    expect(new Set(PV_MODUL_FARBEN).size).toBe(PV_MODUL_FARBEN.length)
    expect(new Set(PV_MODUL_BG).size).toBe(PV_MODUL_BG.length)
  })

  it('Hex-Palette und bg-Palette bleiben gleich lang (Index-Kopplung)', () => {
    expect(PV_MODUL_BG.length).toBe(PV_MODUL_FARBEN.length)
  })
})
