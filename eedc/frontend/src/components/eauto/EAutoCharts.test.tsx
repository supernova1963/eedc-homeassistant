/**
 * N-564 — die Monatstabelle des E-Auto-Hubs kennzeichnet einen Monat „aus Wallbox-Rest".
 *
 * Der Server schickt für einen Monat, in dem das Auto Rest der Wallbox bekommt, aber keine
 * eigene Monatszeile hat, eine Anzeigezeile ohne ID und ohne km mit `ladung_aus_rest`
 * (`dashboard_eauto.py`). Ohne sie ergab die Summe der Tabelle die Kachel „Heimladung" nicht.
 * Die Zeile trägt PV/Netz, km/Fahrverbrauch/V2H stehen als `—` (A3: nicht erfasst), und die
 * Monatszelle nennt die Herkunft mit derselben leisen Notiz wie die Stundentabelle.
 */
import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { EAutoMonatsTabelle, istRestZeile, REST_ZEILE_HINWEIS } from './EAutoCharts'
import type { InvestitionMonatsdaten } from '../../api/investitionen'

const zeile = (monat: number, vd: Record<string, number | boolean>, id: number | null = monat): InvestitionMonatsdaten =>
  ({ id, investition_id: 3, jahr: 2026, monat, verbrauch_daten: vd, einsparung_monat_euro: null, co2_einsparung_kg: null }) as unknown as InvestitionMonatsdaten

const DATEN = [
  zeile(4, { km_gefahren: 1000, verbrauch_kwh: 180, ladung_pv_kwh: 120, ladung_netz_kwh: 80 }),
  zeile(5, { ladung_pv_kwh: 200, ladung_netz_kwh: 200, ladung_kwh: 400, ladung_aus_rest: true }, null),
  zeile(6, { km_gefahren: 800, verbrauch_kwh: 150, ladung_pv_kwh: 90, ladung_netz_kwh: 60 }),
]

describe('EAutoMonatsTabelle — Monat aus Wallbox-Rest (N-564)', () => {
  it('kennzeichnet nur die Restzeile, zeigt ihre Ladung und „—" für das nicht Erfasste', () => {
    render(<EAutoMonatsTabelle monatsdaten={DATEN} />)
    const zeilen = screen.getAllByRole('row').slice(1)          // ohne Kopfzeile
    expect(zeilen).toHaveLength(3)
    const [apr, mai, jun] = zeilen
    const notiz = within(mai).getByText('· aus Wallbox-Rest')
    expect(notiz.getAttribute('title')).toBe(REST_ZEILE_HINWEIS)
    expect(within(apr).queryByText('· aus Wallbox-Rest')).toBeNull()
    expect(within(jun).queryByText('· aus Wallbox-Rest')).toBeNull()

    const zellen = within(mai).getAllByRole('cell').map((c) => c.textContent)
    // Monat · km · kWh · PV · Netz · V2H
    expect(zellen.slice(1)).toEqual(['—', '—', '200,0', '200,0', '—'])
    // Eine erfasste Zeile bleibt wie bisher (km als Zahl, V2H 0,0).
    expect(within(apr).getAllByRole('cell').map((c) => c.textContent).slice(1))
      .toEqual(['1000', '180,0', '120,0', '80,0', '0,0'])
  })

  it('istRestZeile erkennt nur die gekennzeichnete Zeile', () => {
    expect(DATEN.map(istRestZeile)).toEqual([false, true, false])
  })
})

// ─── N-555 Stufe 3 — „aus n Ladevorgängen" (Konzept Heimladung Regel 9) ───────
import { ladevorgaengeNotiz, LADEVORGAENGE_HINWEIS } from './EAutoCharts'

describe('EAutoMonatsTabelle — Monat aus Ladevorgängen (N-555 Stufe 3)', () => {
  const BLOECKE = [
    zeile(7, { km_gefahren: 900, ladung_pv_kwh: 20, ladung_netz_kwh: 10, ladung_aus_bloecken: true, ladevorgaenge_bloecke: 3 }),
    zeile(8, { km_gefahren: 700, ladung_pv_kwh: 30, ladung_netz_kwh: 4, ladung_aus_bloecken: true, ladevorgaenge_bloecke: 5, ladevorgaenge_ungedeckt: 1 }),
    zeile(9, { km_gefahren: 500, ladung_pv_kwh: 9, ladung_netz_kwh: 1, ladung_aus_bloecken: true, ladevorgaenge_bloecke: 1 }),
    zeile(10, { km_gefahren: 100, ladung_pv_kwh: 1, ladung_netz_kwh: 1 }),
  ]

  it('nennt die Zahl der Ladevorgänge und die mit Wallbox-Lücke, sonst nichts', () => {
    expect(BLOECKE.map(ladevorgaengeNotiz)).toEqual([
      'aus 3 Ladevorgängen', 'aus 5 Ladevorgängen, 1 mit Wallbox-Lücke', 'aus 1 Ladevorgang', null,
    ])
  })

  it('zeigt die Notiz in der Monatszelle mit dem Hinweis als Tooltip', () => {
    render(<EAutoMonatsTabelle monatsdaten={BLOECKE} />)
    const [jul, aug, , okt] = screen.getAllByRole('row').slice(1)
    expect(within(jul).getByText('· aus 3 Ladevorgängen').getAttribute('title')).toBe(LADEVORGAENGE_HINWEIS)
    expect(within(aug).getByText('· aus 5 Ladevorgängen, 1 mit Wallbox-Lücke')).toBeTruthy()
    expect(within(okt).queryByText(/Ladevorg/)).toBeNull()
  })
})

// ─── N-569-Ergänzung — „davon aus dem Speicher" (Konzept Heimladung Anhang E) ─────
import { speicherUnterzeile, speicherNotiz } from './EAutoCharts'

describe('E-Auto-Hub — davon aus dem Speicher (N-569)', () => {
  it('Kachel-Unterzeile nur mit einem Wert über 0', () => {
    expect(speicherUnterzeile(31.4)).toBe('davon aus dem Speicher 31 %')
    expect(speicherUnterzeile(0)).toBeUndefined()
    expect(speicherUnterzeile(null)).toBeUndefined()
    expect(speicherUnterzeile(undefined)).toBeUndefined()
  })

  it('Monatstabelle nennt die Speicher-kWh als Notiz, ohne Speicherwert nichts', () => {
    const mit = zeile(7, { km_gefahren: 900, ladung_pv_kwh: 20, ladung_netz_kwh: 10, ladung_speicher_kwh: 6.25 })
    const ohne = zeile(8, { km_gefahren: 700, ladung_pv_kwh: 30, ladung_netz_kwh: 4 })
    expect(speicherNotiz(mit)).toBe('davon 6,3 kWh aus dem Speicher')
    expect(speicherNotiz(ohne)).toBeNull()
    render(<EAutoMonatsTabelle monatsdaten={[mit, ohne]} />)
    const [jul, aug] = screen.getAllByRole('row').slice(1)
    expect(within(jul).getByText('· davon 6,3 kWh aus dem Speicher')).toBeTruthy()
    expect(within(aug).queryByText(/aus dem Speicher/)).toBeNull()
  })
})
