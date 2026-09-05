/**
 * B3 — Matrix-Durchgang Komponenten-Hub (05.09.2026), Client-Hälfte.
 *
 * H-1b: Monatstabelle und Monats-/Saisonvergleich lasen den Strom aus der Rohspalte
 * `stromverbrauch_kwh`. Bei getrennter Strommessung ist die LEER — Strom-Spalte 0,
 * kein Balken im Strom-Modus, während die JAZ daneben aus dem Layer stimmte. Jetzt
 * liest der Client `jaz_je_monat[].strom_kwh` (SoT `get_wp_strom_kwh`), die
 * Rohspalte nur als Fallback für eine ältere Antwort.
 *
 * H-2 / F12: Der Vorbehalt an der Ersparnis steht SICHTBAR unter der Zahl im
 * Kostenvergleich — eine Ersparnis aus geschätzter Wärme oder mit der Wärme eines
 * zweiten Erzeugers darf nicht aussehen wie eine gemessene (SOLL §6, 05.09.2026).
 *
 * N-391 Hub-Teil: Ohne Warmwasser-Achse heißt die Spalte „Wärme", nicht „Heizung".
 *
 * Schwesterdateien: WaermepumpeMonatsTabelle.test.tsx (N-369, dieselbe Tabelle),
 * ../../v4/komponentenAdapter.test.tsx (Status-KPIs des Hubs).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../ui', async (echt) => ({
  ...(await echt<Record<string, unknown>>()),
}))

import { WaermepumpeMonatsTabelle, WaermepumpeKostenvergleich } from './WaermepumpeCharts'
import { stromDesMonats } from './WaermepumpeVergleich'
import type { InvestitionMonatsdaten } from '../../api/investitionen'

/** F7: getrennte Strommessung — KEIN `stromverbrauch_kwh`, der Strom steht je Funktion. */
const f7 = (jahr: number, monat: number) => ({
  id: jahr * 100 + monat, jahr, monat,
  verbrauch_daten: { strom_heizen_kwh: 750, strom_warmwasser_kwh: 250, heizenergie_kwh: 3000, warmwasser_kwh: 600 },
}) as unknown as InvestitionMonatsdaten

const zeitreihe = [{ jahr: 2025, monat: 7, wert: 3.6, grund: null, zaehler_kwh: 3600, nenner_kwh: 1000, strom_kwh: 1000 }]

describe('B3/H-1b — der Strom kommt aus der Layer-Zeitreihe', () => {
  it('Monatstabelle: Strom-Spalte 1.000 bei getrennter Messung (vorher 0)', () => {
    render(<WaermepumpeMonatsTabelle monatsdaten={[f7(2025, 7)]} jazJeMonat={zeitreihe} />)
    expect(screen.getByText('1.000')).toBeInTheDocument()
    expect(screen.queryByText('0')).not.toBeInTheDocument()
  })

  it('stromDesMonats: Layer-Wert vor Rohspalte, Rohspalte nur ohne das Feld', () => {
    expect(stromDesMonats(f7(2025, 7), zeitreihe)).toBe(1000)
    // Ältere Antwort ohne `strom_kwh` → Rohspalte (hier leer → 0), keine Erfindung.
    expect(stromDesMonats(f7(2025, 7), [{ jahr: 2025, monat: 7 }])).toBe(0)
    expect(stromDesMonats(f7(2025, 7), undefined)).toBe(0)
    const f2 = { ...f7(2025, 7), verbrauch_daten: { stromverbrauch_kwh: 420 } } as unknown as InvestitionMonatsdaten
    expect(stromDesMonats(f2, undefined)).toBe(420)
    // ⭐ Reihenfolge, nicht nur Fallback: Sind BEIDE da und verschieden, gilt der
    // Layer — die Rohspalte kann bei parallel gepflegtem Gesamtsensor einen
    // anderen Wert tragen als der SoT (#183). Ein Sprengsatz „Rohspalte zuerst"
    // blieb ohne diesen Fall stumm (gemessen 05.09.2026).
    expect(stromDesMonats(f2, [{ jahr: 2025, monat: 7, strom_kwh: 1000 }])).toBe(1000)
  })
})

describe('B3/N-391 — ohne Warmwasser-Achse ist es „Wärme", nicht „Heizung"', () => {
  it('Tabellenkopf', () => {
    render(<WaermepumpeMonatsTabelle monatsdaten={[f7(2025, 7)]} jazJeMonat={zeitreihe} hatWarmwasserAchse={false} />)
    expect(screen.getByText('Wärme (kWh)')).toBeInTheDocument()
    expect(screen.queryByText('Heizung (kWh)')).not.toBeInTheDocument()
    expect(screen.queryByText('Warmwasser (kWh)')).not.toBeInTheDocument()
  })

  it('mit beiden Achsen bleibt „Heizung" (vertraute Anzeige)', () => {
    render(<WaermepumpeMonatsTabelle monatsdaten={[f7(2025, 7)]} jazJeMonat={zeitreihe} />)
    expect(screen.getByText('Heizung (kWh)')).toBeInTheDocument()
  })
})

describe('B3/H-2 + F12 — der Vorbehalt steht sichtbar unter der Ersparnis', () => {
  const z = (over: Record<string, unknown>) => ({
    wp_kosten_euro: 300, alte_heizung_kosten_euro: 466.67, ersparnis_euro: 166.67, ...over,
  }) as unknown as Parameters<typeof WaermepumpeKostenvergleich>[0]['zusammenfassung']

  it('geschätzte Wärme: der Satz aus dem Layer erscheint', () => {
    render(<WaermepumpeKostenvergleich zusammenfassung={z({ ersparnis_vorbehalt: 'Wärme geschätzt — Ersparnis und CO₂ folgen aus der Schätzung' })} />)
    expect(screen.getByText('Wärme geschätzt — Ersparnis und CO₂ folgen aus der Schätzung')).toBeInTheDocument()
  })

  it('gemessene Wärme ohne Vorbehalt: kein Satz', () => {
    render(<WaermepumpeKostenvergleich zusammenfassung={z({ ersparnis_vorbehalt: null })} />)
    expect(screen.queryByText(/geschätzt|zweiter Erzeuger/)).not.toBeInTheDocument()
  })
})
