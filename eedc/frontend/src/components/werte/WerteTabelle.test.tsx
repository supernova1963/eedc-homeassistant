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
    wp_waerme: null, wp_strom: null, wp_cop: null, wp_cop_grund: null,
    wp_strom_heizen: null, wp_strom_warmwasser: null,
    wp_waerme_heizen: null, wp_waerme_warmwasser: null,
    eauto_km: null, eauto_ladung: null, eauto_pv_anteil: null,
    wallbox_ladung: null, wallbox_pv_ladung: null, wallbox_pv_anteil: null,
    sonstiges_erzeugung: null, sonstiges_verbrauch: null,
    einspeise_erloes: 5, ev_ersparnis: 12, netzbezug_kosten: 9,
    netto_ertrag: 8, netto_bilanz: 8, ust_eigenverbrauch: 0, netzbezug_preis_cent: null, co2_einsparung: 25,
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
    speicher_ladung: null, speicher_entladung: null, speicher_effizienz: null, speicher_effizienz_quelle: null,
    speicher_vollzyklen: null,
    wp_strom: null,
    sonstiges_erzeugung: null, sonstiges_verbrauch: null,
    einspeise_erloes: 1, ev_ersparnis: 2, netzbezug_kosten: 1.5,
    netto_ertrag: 3, netto_bilanz: 1.5, co2_einsparung: 11.4,
    ueberschuss_kwh: 8, defizit_kwh: 2, peak_pv_kw: 6.2,
    peak_netzbezug_kw: 1.1, peak_einspeisung_kw: 4.0, grundlast_kw: 0.38,
    performance_ratio: 0.85, batterie_vollzyklen: 0.4,
    temperatur_min_c: 10, temperatur_max_c: 22,
    strahlung_summe_wh_m2: 5000, gti_summe_wh_m2: null, boersenpreis_avg_cent: 9.5,
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
    // Grundlast je Nacht steht als WÄHLBARE Spalte im Picker (OB73-gif, #395) —
    // nicht voreingestellt, wie alle Zusatzspalten seit rapahls Sonstiges-Wunsch.
    expect(screen.getByText('Grundlast')).toBeInTheDocument()
  })

  it('Grundlast je Nacht wird gerendert — und ein „—" ist kein 0,00 kW', () => {
    const tage = [
      tw('2026-05-10', { grundlast_kw: 0.38 }),
      tw('2026-05-11', { grundlast_kw: null }),   // keine Nachtstunde gemessen
    ].map(tagesZeile)
    render(
      <WerteTabelle rows={tage} granularitaet="tag" defaultSpalten={['grundlast_kw']} />,
    )
    expect(screen.getByText(/Grundlast \(kW\)/)).toBeInTheDocument()
    expect(screen.getByText('0,38')).toBeInTheDocument()
    // Der Total-Fall trägt das Display-Token, keine erfundene Null.
    expect(screen.queryByText('0,00')).not.toBeInTheDocument()
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

  // Striker, T89667 #162 — beide Zahlenpaare sind seinem Screenshot der
  // Tageswerte (Januar 2026, Einspeisung) entnommen, nicht erfunden.
  describe('Δ erklärt die zwei Spalten daneben (T89667 #162)', () => {
    /** Δ-Zelle der ersten Metrik-Spalte einer Datenzeile. */
    function deltaZelleDerErstenZeile() {
      const zeilen = screen.getAllByRole('row')
      return within(zeilen[2]).getAllByRole('cell')[3]
    }

    function zeigeTagesVergleich(aktuellEinsp: number, vergleichEinsp: number) {
      const aktuell = [tw('2026-01-27', { einspeisung: aktuellEinsp })].map(tagesZeile)
      const vergleich = [tw('2025-12-27', { einspeisung: vergleichEinsp })]
        .map(tagesZeile)
        .map((z) => ({ ...z, vergleichKey: aktuell[0].vergleichKey }))
      render(
        <WerteTabelle
          rows={aktuell} vorjahrRows={vergleich} granularitaet="tag"
          jahrLabel="Jan" vergleichLabel="Dez" vergleichDefaultAn
          defaultSpalten={['einspeisung']}
        />,
      )
    }

    it('0 gegen 12 ergibt 12, nicht 11', () => {
      // Vorher: die Spalten rundeten auf „0" und „12", die Δ-Spalte rechnete
      // 11,71 − 0,29 weiter und schrieb „▼ 11 (−97,6 %)" daneben.
      zeigeTagesVergleich(0.29, 11.71)
      const delta = deltaZelleDerErstenZeile()
      expect(delta).toHaveTextContent('▼ 12')
      expect(delta).not.toHaveTextContent('11')
      expect(delta).toHaveTextContent('100,0 %')
    })

    it('zweimal 0 nebeneinander behauptet keinen Unterschied', () => {
      // Vorher: „= 0" wäre richtig gewesen, dastand „▼ 0 (−73,3 %)".
      zeigeTagesVergleich(0.12, 0.45)
      const delta = deltaZelleDerErstenZeile()
      expect(delta).toHaveTextContent('=')
      expect(delta).not.toHaveTextContent('%')
    })
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

/**
 * N-374 — der Grund zu einer gesperrten Kennzahl steht SICHTBAR unter der Tabelle.
 *
 * ⚑ Was diese Probe misst, und warum die Zusicherung auf die HÖHE zielt statt auf
 * eine Symmetrie: Bis zum 2026-09-04 trug die Zelle den Grund allein in einem
 * nativen `title=`. Der Wert war damit korrekt beim Anwender „angekommen" — im
 * Sinne des DOM. Erreichbar war er trotzdem nur, wenn man auf den Gedanken kam,
 * die Zelle anzufassen: nichts wies darauf hin, dass hinter dem „—" etwas steht
 * (das Info-Icon der Haus-Tooltips trägt `hidden sm:`, `ui/FormelTooltip.tsx:92`).
 * Eine Probe, die nur geprüft hätte, DASS der Grund irgendwo im Markup vorkommt,
 * wäre über beide Zustände grün gewesen — deshalb prüft diese hier ausdrücklich
 * einen **Textknoten** (`getByText` sieht Attribute nicht) und zusätzlich, dass
 * die Zelle selbst weiterhin nur das „—" trägt.
 *
 * ⛔ **Berichtigung 2026-09-04 (N-390):** Hier stand „Auf dem Telefon gibt es für
 * `title=` keine Entsprechung." Das ist falsch — `App.tsx` ruft
 * `useTouchTitleTooltip` auf, einen app-globalen Touch-Ersatz. Der Befund oben
 * hält ohne diesen Satz; er beruhte nie auf ihm, sondern auf der Auffindbarkeit.
 *
 * Gegenprobe in derselben Datei: eine Zeile mit gebildeter Kennzahl darf den
 * Satz NICHT erzeugen, sonst erklärt die Tabelle etwas, das gar nicht eintritt.
 */
describe('WerteTabelle — gesperrte Kennzahl nennt ihren Grund sichtbar (N-374)', () => {
  beforeEach(() => localStorage.clear())

  function mitCopSpalte(rows: ReturnType<typeof monatsZeile>[]) {
    render(<WerteTabelle rows={rows} granularitaet="monat" />)
    fireEvent.click(screen.getByRole('button', { name: /Spalten/ }))
    const label = screen.getByText('WP COP').closest('label')!
    fireEvent.click(within(label).getByRole('checkbox'))
  }

  const GRUND = 'kein Wärmemengenzähler zugeordnet'

  it('nennt den Grund als sichtbaren Text unter der Tabelle', () => {
    mitCopSpalte([
      mz(1, 2025, { wp_cop: null, wp_cop_grund: GRUND }),
      mz(2, 2025, { wp_cop: null, wp_cop_grund: GRUND }),
    ].map(monatsZeile))

    // Sichtbarer Textknoten — ein `title=` würde hier NICHT gefunden.
    const zeile = screen.getByText(`WP COP: ${GRUND}`)
    expect(zeile).toBeInTheDocument()
    // Und er steht genau EINMAL, obwohl beide Monate ihn tragen: derselbe Satz
    // je Zeile wäre Rauschen statt Auskunft.
    expect(screen.getAllByText(`WP COP: ${GRUND}`)).toHaveLength(1)
  })

  it('lässt die Zelle selbst beim „—" — der Grund ersetzt den Wert nicht', () => {
    mitCopSpalte([mz(1, 2025, { wp_cop: null, wp_cop_grund: GRUND })].map(monatsZeile))
    const zellen = Array.from(document.querySelectorAll('tbody td')).map((td) => td.textContent?.trim())
    expect(zellen).toContain('—')
    // Der lange Grundtext gehört NICHT in die Zelle (Spaltenbreite).
    expect(zellen.some((t) => t?.includes(GRUND))).toBe(false)
  })

  it('Gegenprobe: eine gebildete Kennzahl erzeugt keinen Grund-Satz', () => {
    mitCopSpalte([mz(1, 2025, { wp_cop: 3.4, wp_cop_grund: GRUND })].map(monatsZeile))
    expect(screen.queryByText(new RegExp(GRUND))).not.toBeInTheDocument()
  })
})
