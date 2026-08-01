import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { WerteTabelle } from './WerteTabelle'
import type { MonatsZeitreihe } from '../../pages/auswertung/types'
import type { TagWerte } from '../../api/energie_profil'
import { monatsZeile, tagesZeile, richteMonateAus } from '../../lib/werte'

// Der CSV-Knopf löst im echten Code einen Download aus — für den Abgleich
// Tabelle ↔ Export mocken (dieselbe Technik wie in `lib/werte/werte.test.ts`).
vi.mock('../../utils/export', () => ({ exportToCSV: vi.fn() }))
import { exportToCSV } from '../../utils/export'

function mz(monat: number, jahr: number, over: Partial<MonatsZeitreihe> = {}): MonatsZeitreihe {
  return {
    name: `${monat}/${jahr}`, jahr, monat,
    erzeugung: 100 * monat, eigenverbrauch: 60, einspeisung: 40, netzbezug: 30,
    gesamtverbrauch: 90, direktverbrauch: 50,
    autarkie: 70, evQuote: 60, spezErtrag: 80,
    globalstrahlung: null, sonnenstunden: null,
    speicher_ladung: null, speicher_entladung: null, speicher_effizienz: null,
    wp_waerme: null, wp_strom: null, wp_cop: null,
    wp_strom_heizen: null, wp_strom_warmwasser: null,
    wp_waerme_heizen: null, wp_waerme_warmwasser: null,
    eauto_km: null, eauto_ladung: null, eauto_pv_anteil: null,
    wallbox_ladung: null, wallbox_pv_ladung: null, wallbox_pv_anteil: null,
    einspeise_erloes: 5, ev_ersparnis: 12, netzbezug_kosten: 9,
    netto_ertrag: 8, netto_bilanz: 8, netzbezug_preis_cent: null, co2_einsparung: 25,
    ...over,
  }
}

function tw(datum: string, over: Partial<TagWerte> = {}): TagWerte {
  return {
    datum, stunden_verfuegbar: 24, datenquelle: 'ha_sensor',
    erzeugung: 30, eigenverbrauch: 18, einspeisung: 12, netzbezug: 6,
    pv_anlage: 24, bkw: 6,
    gesamtverbrauch: 24, direktverbrauch: 15,
    autarkie: 75, evQuote: 60, spezErtrag: 3,
    speicher_ladung: null, speicher_entladung: null, speicher_effizienz: null,
    speicher_vollzyklen: null,
    wp_strom: null,
    einspeise_erloes: 1, ev_ersparnis: 2, netzbezug_kosten: 1.5,
    netto_ertrag: 3, netto_bilanz: 1.5, co2_einsparung: 11.4,
    ueberschuss_kwh: 8, defizit_kwh: 2, peak_pv_kw: 6.2,
    peak_netzbezug_kw: 1.1, peak_einspeisung_kw: 4.0,
    performance_ratio: 0.85, batterie_vollzyklen: 0.4,
    temperatur_min_c: 10, temperatur_max_c: 22,
    strahlung_summe_wh_m2: 5000, boersenpreis_avg_cent: 9.5,
    boersenpreis_min_cent: -1, negative_preis_stunden: 1,
    einspeisung_neg_preis_kwh: 0,
    ...over,
  }
}

const monatsRows = [mz(1, 2025), mz(2, 2025)].map(monatsZeile)

describe('WerteTabelle', () => {
  beforeEach(() => localStorage.clear())

  it('Steuerung (Picker/CSV) + Default-Spalten + Footer — überall identisch', () => {
    render(<WerteTabelle rows={monatsRows} granularitaet="monat" />)
    expect(screen.getByRole('button', { name: /Spalten/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /CSV/ })).toBeInTheDocument()
    expect(screen.getByText(/PV-Erzeugung \(kWh\)/)).toBeInTheDocument()
    expect(screen.getByText('2 Monate')).toBeInTheDocument()
  })

  it('Spalten-Picker blendet eine Spalte aus', () => {
    render(<WerteTabelle rows={monatsRows} granularitaet="monat" />)
    expect(screen.getByText(/PV-Erzeugung \(kWh\)/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Spalten/ }))
    const pickerLabel = screen.getByText('PV-Erzeugung').closest('label')!
    fireEvent.click(within(pickerLabel).getByRole('checkbox'))
    expect(screen.queryByText(/PV-Erzeugung \(kWh\)/)).not.toBeInTheDocument()
  })

  it('Cockpit-Platzierung hat dieselbe Funktion (Picker/CSV) + Cross-Link', () => {
    render(<WerteTabelle rows={monatsRows} granularitaet="monat" alleWerteHref="/v4/auswertungen/tabelle" />)
    expect(screen.getByRole('button', { name: /Spalten/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /CSV/ })).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /Alle Werte/ })
    expect(link).toHaveAttribute('href', '/v4/auswertungen/tabelle')
  })

  it('Vergleich-Toggle erscheint bei Vergleichs-Daten und schaltet Δ frei', () => {
    render(
      <WerteTabelle
        rows={monatsRows}
        vorjahrRows={richteMonateAus([mz(1, 2024), mz(2, 2024)].map(monatsZeile))}
        granularitaet="monat"
        jahrLabel={2025}
        vergleichLabel={2024}
      />,
    )
    const toggle = screen.getByRole('button', { name: /Vergleich 2024/ })
    fireEvent.click(toggle)
    expect(screen.getAllByText(/[▲▼=]/).length).toBeGreaterThan(0)
  })

  it('Spalten-Sortierung: Klick auf Metrik-Header sortiert absteigend, Default bleibt chronologisch (IST-Parität)', () => {
    render(<WerteTabelle rows={monatsRows} granularitaet="monat" />)
    // Default chronologisch aufsteigend: Jan (erzeugung 100) vor Feb (200).
    // Zeitraum ist R20-1b in Monatskürzel + Jahr gesplittet → „Jan" statt „Jan 2025".
    let rows = screen.getAllByRole('row')
    expect(within(rows[1]).getByText('Jan')).toBeInTheDocument()
    // Klick auf „PV-Erzeugung" → absteigend nach Wert → Feb (200) zuerst.
    fireEvent.click(screen.getByRole('button', { name: /PV-Erzeugung/ }))
    rows = screen.getAllByRole('row')
    expect(within(rows[1]).getByText('Feb')).toBeInTheDocument()
  })

  it('R20-1b: Zeitraum-Split — Monatskürzel und Jahr als getrennte Teil-Spalten', () => {
    render(<WerteTabelle rows={monatsRows} granularitaet="monat" />)
    // Monatskürzel links, Jahr rechts — nicht mehr ein zusammenhängendes „Jan 2025".
    expect(screen.getByText('Jan')).toBeInTheDocument()
    expect(screen.getByText('Feb')).toBeInTheDocument()
    expect(screen.getAllByText('2025').length).toBe(2)
    expect(screen.queryByText('Jan 2025')).not.toBeInTheDocument()
  })

  it('R20-1a: Vergleich beschriftet die Sub-Spalten (aktuell · Vergleich · Δ)', () => {
    render(
      <WerteTabelle
        rows={monatsRows}
        vorjahrRows={richteMonateAus([mz(1, 2024), mz(2, 2024)].map(monatsZeile))}
        granularitaet="monat"
        jahrLabel={2025}
        vergleichLabel={2024}
        vergleichDefaultAn
      />,
    )
    // Δ-Sub-Header je Metrik-Gruppe.
    expect(screen.getAllByText('Δ').length).toBeGreaterThan(0)
    // Perioden-Label als eigener Spaltenkopf (aktuell = 2025, Vergleich = 2024).
    const heads = screen.getAllByRole('columnheader')
    expect(heads.some((h) => h.textContent === '2025')).toBe(true)
    expect(heads.some((h) => h.textContent === '2024')).toBe(true)
  })

  it('Tages-Granularität: Tag-native Spalte sichtbar, Footer „Tage", kein WP-Wärme', () => {
    const tage = [tw('2026-05-10'), tw('2026-05-11')].map(tagesZeile)
    render(<WerteTabelle rows={tage} granularitaet="tag" />)
    // Tag-natives Default-Feld (Überschuss / Peak PV) erscheint
    expect(screen.getByText(/Überschuss \(kWh\)/)).toBeInTheDocument()
    expect(screen.getByText('2 Tage')).toBeInTheDocument()
    // Picker zeigt keinen monat-only Eintrag „WP Wärme"
    fireEvent.click(screen.getByRole('button', { name: /Spalten/ }))
    expect(screen.queryByText('WP Wärme')).not.toBeInTheDocument()
  })

  it('Tages-Vergleich matcht über den ausgerichteten Schlüssel (nicht über den Tag-im-Monat)', () => {
    // Die Ausrichtung macht der Aufrufer (`richteAus` in AuswertungenTabelleV4) —
    // hier nachgestellt: die Vergleichszeile trägt den Schlüssel ihrer Primärzeile.
    const aktuell = [tw('2026-05-10', { erzeugung: 30 })].map(tagesZeile)
    const vergleich = [tw('2026-04-10', { erzeugung: 20 })]
      .map(tagesZeile)
      .map((z) => ({ ...z, vergleichKey: aktuell[0].vergleichKey }))
    render(
      <WerteTabelle
        rows={aktuell}
        vorjahrRows={vergleich}
        granularitaet="tag"
        jahrLabel="Mai"
        vergleichLabel="Apr"
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /Vergleich Apr/ }))
    expect(screen.getAllByText(/[▲▼=]/).length).toBeGreaterThan(0)
  })

  // PN 90204 (Rainer): über „Alle Jahre" lagen mehrere Jahrgänge desselben Monats
  // im Vergleichsfenster — jede Zeile verglich sich mit dem jüngsten, Dez 2025 im
  // Extremfall mit sich selbst (Δ 0,0 %).
  it('mehrjährig: jede Zeile zeigt ihr echtes Vorjahr, fehlendes Vorjahr „—"', () => {
    const prim = [mz(12, 2024, { erzeugung: 227.9 }), mz(12, 2025, { erzeugung: 432.7 })].map(monatsZeile)
    const fenster = richteMonateAus(
      [mz(12, 2024, { erzeugung: 227.9 }), mz(12, 2025, { erzeugung: 432.7 })].map(monatsZeile),
    )
    render(
      <WerteTabelle
        rows={prim} vorjahrRows={fenster} granularitaet="monat"
        jahrLabel="Aktuell" vergleichLabel="Vorjahr" vergleichDefaultAn
      />,
    )
    const zeilen = screen.getAllByRole('row')
    // Kopf (2 Zeilen im Vergleichs-Modus) → Datenzeilen ab Index 2, danach der Fuß.
    const dez2024 = within(zeilen[2]).getAllByRole('cell')
    const dez2025 = within(zeilen[3]).getAllByRole('cell')
    // Spalte 0 = Zeitraum, dann je Metrik: aktuell · Vergleich · Δ (1. Metrik = PV-Erzeugung).
    expect(dez2024[1]).toHaveTextContent('228')
    expect(dez2024[2]).toHaveTextContent('—')   // kein Dez 2023 → kein gespiegelter Wert
    expect(dez2024[3]).toHaveTextContent('—')
    expect(dez2025[1]).toHaveTextContent('433')
    expect(dez2025[2]).toHaveTextContent('228') // Dez 2025 ← Dez 2024, NICHT 433/433
    expect(dez2025[3]).toHaveTextContent('▲')
    // Fuß: „aktuell" bleibt die Spaltensumme, der Vergleich schweigt — nur eine der
    // beiden Zeilen ist gepaart, eine Summe wäre eine andere Zeitspanne.
    const fuss = within(screen.getAllByRole('row').at(-1)!).getAllByRole('cell')
    expect(fuss[1]).toHaveTextContent('661')
    expect(fuss[2]).toHaveTextContent('—')
    expect(fuss[3]).toHaveTextContent('—')
  })

  it('Summenzeile vergleicht, wenn jede Zeile ein Gegenstück hat', () => {
    render(
      <WerteTabelle
        rows={[mz(1, 2025, { erzeugung: 100 }), mz(2, 2025, { erzeugung: 200 })].map(monatsZeile)}
        vorjahrRows={richteMonateAus([mz(1, 2024, { erzeugung: 50 }), mz(2, 2024, { erzeugung: 50 })].map(monatsZeile))}
        granularitaet="monat" jahrLabel={2025} vergleichLabel={2024} vergleichDefaultAn
      />,
    )
    const fuss = within(screen.getAllByRole('row').at(-1)!).getAllByRole('cell')
    expect(fuss[1]).toHaveTextContent('300')
    expect(fuss[2]).toHaveTextContent('100')
  })

  // Gegenlese-Auflage zu PN 90204: der schweigende Fuß braucht einen sichtbaren
  // Grund. Genau in „Alle Jahre" war die fehlende Vergleichszahl der gemeldete
  // Fehler — ohne Begründung liest sich die Korrektur wie der Bug.
  describe('schweigender Fuß nennt seinen Grund', () => {
    const prim = [mz(12, 2024, { erzeugung: 227.9 }), mz(12, 2025, { erzeugung: 432.7 })].map(monatsZeile)
    const fenster = richteMonateAus(
      [mz(12, 2024, { erzeugung: 227.9 }), mz(12, 2025, { erzeugung: 432.7 })].map(monatsZeile),
    )

    it('Hinweistext mit Anzahl — sichtbar, nicht nur als Tooltip', () => {
      render(
        <WerteTabelle
          rows={prim} vorjahrRows={fenster} granularitaet="monat"
          jahrLabel="Aktuell" vergleichLabel="Vorjahr" vergleichDefaultAn
        />,
      )
      expect(screen.getByText(/Summenzeile zeigt keinen Vergleich/)).toHaveTextContent(
        '1 von 2 Monaten hat kein Gegenstück',
      )
      // Derselbe Satz hängt am leeren Fuß (Hover).
      const fuss = within(screen.getAllByRole('row').at(-1)!).getAllByRole('cell')
      expect(fuss[2]).toHaveAttribute('title', expect.stringContaining('kein Gegenstück'))
    })

    it('Tages-Granularität beugt in „Tagen"', () => {
      const aktuell = [tw('2026-05-10'), tw('2026-05-11')].map(tagesZeile)
      // Nur der zweite Tag hat ein Gegenstück (Schlüssel auf die Primärzeile gehoben).
      const vergleich = [tw('2026-04-11')].map(tagesZeile).map((z) => ({ ...z, vergleichKey: aktuell[1].vergleichKey }))
      render(
        <WerteTabelle
          rows={aktuell} vorjahrRows={vergleich} granularitaet="tag"
          jahrLabel="Mai" vergleichLabel="Apr" vergleichDefaultAn
        />,
      )
      expect(screen.getByText(/Summenzeile zeigt keinen Vergleich/)).toHaveTextContent('1 von 2 Tagen hat')
    })

    it('vollständig gepaart ⇒ kein Hinweis, kein Tooltip', () => {
      render(
        <WerteTabelle
          rows={[mz(1, 2025), mz(2, 2025)].map(monatsZeile)}
          vorjahrRows={richteMonateAus([mz(1, 2024), mz(2, 2024)].map(monatsZeile))}
          granularitaet="monat" jahrLabel={2025} vergleichLabel={2024} vergleichDefaultAn
        />,
      )
      expect(screen.queryByText(/Summenzeile zeigt keinen Vergleich/)).not.toBeInTheDocument()
      const fuss = within(screen.getAllByRole('row').at(-1)!).getAllByRole('cell')
      expect(fuss[2]).not.toHaveAttribute('title')
    })

    it('ohne eingeschalteten Vergleich bleibt der Hinweis weg', () => {
      render(
        <WerteTabelle
          rows={prim} vorjahrRows={fenster} granularitaet="monat"
          jahrLabel="Aktuell" vergleichLabel="Vorjahr"
        />,
      )
      expect(screen.queryByText(/Summenzeile zeigt keinen Vergleich/)).not.toBeInTheDocument()
    })
  })

  // Gegenlese-Auflage zu PN 90204: Tabelle und CSV teilen sich EINE
  // Vergleichs-Auflösung (`lib/werte/vergleich`) — hier gegengeprüft, dass der
  // Export bei derselben Eingabe dieselbe Fuß-Aussage trägt. Tabelle ↔ Export ist
  // historisch die Stelle, an der es auseinanderlief.
  describe('Fuß: Tabelle und CSV-Export sagen dasselbe', () => {
    beforeEach(() => vi.mocked(exportToCSV).mockClear())

    function exportiereUndLiesFuss() {
      fireEvent.click(screen.getByRole('button', { name: /CSV/ }))
      const [, out] = vi.mocked(exportToCSV).mock.calls[0]
      return out[out.length - 1] // Aggregat-Zeile: [Label, aktuell, Vergleich, Δ, …]
    }

    it('unvollständig gepaart: Tabelle „—", Export leere Zellen', () => {
      render(
        <WerteTabelle
          rows={[mz(12, 2024, { erzeugung: 227.9 }), mz(12, 2025, { erzeugung: 432.7 })].map(monatsZeile)}
          vorjahrRows={richteMonateAus(
            [mz(12, 2024, { erzeugung: 227.9 }), mz(12, 2025, { erzeugung: 432.7 })].map(monatsZeile),
          )}
          granularitaet="monat" jahrLabel="Aktuell" vergleichLabel="Vorjahr" vergleichDefaultAn
        />,
      )
      const fuss = within(screen.getAllByRole('row').at(-1)!).getAllByRole('cell')
      expect(fuss[2]).toHaveTextContent('—')
      const csvFuss = exportiereUndLiesFuss()
      expect(csvFuss[0]).toBe('2 Monate')
      expect(csvFuss[1]).toBe(660.6) // „aktuell" bleibt die Spaltensumme — in beiden
      expect(csvFuss[2]).toBe('')    // Vergleich schweigt — in beiden
      expect(csvFuss[3]).toBe('')
    })

    it('vollständig gepaart: beide zeigen dieselbe Vergleichssumme', () => {
      render(
        <WerteTabelle
          rows={[mz(1, 2025, { erzeugung: 100 }), mz(2, 2025, { erzeugung: 200 })].map(monatsZeile)}
          vorjahrRows={richteMonateAus([mz(1, 2024, { erzeugung: 50 }), mz(2, 2024, { erzeugung: 50 })].map(monatsZeile))}
          granularitaet="monat" jahrLabel={2025} vergleichLabel={2024} vergleichDefaultAn
        />,
      )
      const fuss = within(screen.getAllByRole('row').at(-1)!).getAllByRole('cell')
      expect(fuss[1]).toHaveTextContent('300')
      expect(fuss[2]).toHaveTextContent('100')
      const csvFuss = exportiereUndLiesFuss()
      expect(csvFuss[1]).toBe(300)
      expect(csvFuss[2]).toBe(100)
      expect(csvFuss[3]).toBe(200)
    })
  })
})
