/**
 * B5 — die Kurve zum Sonnenangebot (#395 Punkt 1, Melder OB73-gif).
 *
 * **Zwei Serien, und beide müssen da sein.** Die Globalstrahlung ist die für PV
 * physikalisch tragende und über die Anbieter hinweg vergleichbare Größe
 * (12–16 % Unterschied), die Sonnenstunden sind die verständliche, aber die
 * schwächere (Faktor 1,6–2,0 zwischen Open-Meteo und Bright Sky). Nur die
 * Stunden zu zeigen hieße, die schwächere Größe allein zu lassen; nur die
 * Strahlung zu zeigen hieße, die Frage des Melders nicht zu beantworten.
 *
 * ⚠ **jsdom-Grenze (im Haus bekannt):** Recharts misst seinen Container über
 * `ResponsiveContainer` und zeichnet in jsdom keine Balken. Geprüft wird darum
 * die **Datenaufbereitung** (reine Funktionen) und die **Serien-Deklaration**
 * am Quelltext — keine Pixel. Dieselbe Linie wie `CockpitJahrV4.test.tsx`.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, it, expect } from 'vitest'
import type { AggregierteMonatsdaten } from '../../api/monatsdaten'
import {
  SONNENANGEBOT_SPALTEN, baueSonnenangebot, hatSonnenangebot,
} from './SonnenangebotTeile'

const QUELLE = readFileSync(
  join(process.cwd(), 'src', 'components', 'prognose', 'SonnenangebotTeile.tsx'),
  'utf8',
)

function zeile(
  jahr: number, monat: number,
  ghi: number | null, sonne: number | null,
): AggregierteMonatsdaten {
  return {
    id: 1, anlage_id: 1, jahr, monat,
    einspeisung_kwh: 0, netzbezug_kwh: 0,
    globalstrahlung_kwh_m2: ghi, sonnenstunden: sonne,
  } as unknown as AggregierteMonatsdaten
}

describe('Sonnenangebot — Datenaufbereitung', () => {
  it('sortiert über Jahresgrenzen hinweg und beschriftet MM/JJJJ', () => {
    const punkte = baueSonnenangebot([
      zeile(2026, 1, 25.3, 85),
      zeile(2025, 12, 22.0, 40),
    ])
    expect(punkte.map((p) => p.monat)).toEqual(['12/2025', '01/2026'])
  })

  it('lässt einen Monat ohne Wetterwert als Lücke stehen, statt ihn wegzulassen', () => {
    // Eine herausgelassene Lücke sähe aus wie ein durchgehender Verlauf — genau
    // die Aussage, die dieser Block widerlegen soll.
    const punkte = baueSonnenangebot([
      zeile(2025, 6, 192.9, 231.8),
      zeile(2025, 7, null, null),
      zeile(2025, 8, 150.0, 200.0),
    ])
    expect(punkte).toHaveLength(3)
    expect(punkte[1]).toEqual({ monat: '07/2025', globalstrahlung: null, sonnenstunden: null })
  })

  it('meldet eine Reihe ganz ohne Wetterwerte als leer', () => {
    expect(hatSonnenangebot(baueSonnenangebot([zeile(2025, 7, null, null)]))).toBe(false)
    expect(hatSonnenangebot(baueSonnenangebot([zeile(2025, 7, null, 231.8)]))).toBe(true)
    expect(hatSonnenangebot(baueSonnenangebot([zeile(2025, 7, 192.9, null)]))).toBe(true)
  })
})

describe('Sonnenangebot — beide Serien', () => {
  it('der Chart deklariert Globalstrahlung UND Sonnenstunden', () => {
    // Ohne beide wäre der Block eine halbe Antwort: die Strahlung ohne die
    // verständliche Größe, oder die Stunden ohne die belastbare.
    expect(QUELLE).toMatch(/dataKey="globalstrahlung"/)
    expect(QUELLE).toMatch(/dataKey="sonnenstunden"/)
  })

  it('jede Serie hat ihre eigene Y-Achse — zwei Einheiten, zwei Skalen', () => {
    expect(QUELLE).toMatch(/yAxisId="ghi"/)
    expect(QUELLE).toMatch(/yAxisId="sonne"/)
    expect(QUELLE).toMatch(/orientation="right"/)
  })

  it('die Tabellen-Ablesung führt dieselben zwei Größen mit ihren Einheiten', () => {
    expect(SONNENANGEBOT_SPALTEN.map((s) => s.key)).toEqual([
      'globalstrahlung', 'sonnenstunden',
    ])
    expect(SONNENANGEBOT_SPALTEN.map((s) => s.einheit)).toEqual(['kWh/m²', 'h'])
    // ⛔ Keine Summenzeile: ein Jahres-Σ über kWh/m² und Stunden ist keine Größe,
    // die jemand braucht — und eine falsche Summe ist schlimmer als keine.
    expect(SONNENANGEBOT_SPALTEN.every((s) => s.summierbar === false)).toBe(true)
  })

  it('die Farben kommen aus der Zentrale, nicht aus dem Chart', () => {
    // Regel 0a: keine Inline-Hex-Farbe außerhalb `lib/colors.ts`.
    expect(QUELLE).toMatch(/CHART_COLORS\.strahlung/)
    expect(QUELLE).toMatch(/CHART_COLORS\.sonnenstunden/)
    expect(QUELLE).not.toMatch(/#[0-9a-fA-F]{6}/)
  })
})
