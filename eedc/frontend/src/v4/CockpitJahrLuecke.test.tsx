/**
 * Cockpit/Jahr — die Jahreszahl über der Lücke (Fund N-65, Paket P-12).
 *
 * Nachgestellt ist die Lage der Box am 02.08.2026: das laufende Jahr hat aggregierte
 * Zeilen bis Juni, Juli ist gelaufen und trägt Daten, hat aber noch keinen
 * Monatsabschluss — August läuft.
 *
 * Geprüft wird die Trennung, die P-12 einführt (Entscheid Gernot 2026-08-02):
 *  - **Kachel** = das Jahr bis heute (Jan–Aug), inkl. dem laufenden Monat;
 *  - **Vergleichstabelle** = die abgeschlossenen Monate (Jan–Jul) auf BEIDEN Seiten,
 *    damit kein Delta acht IST-Monate gegen sieben Vorjahres-Monate stellt;
 *  - der Unterschied steht an der Kachel, über der IST-Spalte und im Fuß.
 *
 * Eigene Datei statt Ausbau von `CockpitJahrV4.test.tsx`: die Fixture braucht eine
 * feste Systemzeit und einen Endpoint, der zwischen „Monat mit Daten" und „Monat vor
 * der Inbetriebnahme" unterscheidet.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, fireEvent, within } from '@testing-library/react'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'
import type { Nachhaltigkeit } from '../api/cockpit'
import { aktuellerMonat, monatsZeile } from '../test/factories'
import { renderMitProvidern, stubMatchMedia } from '../test/render'

const bis = (n: number) => Array.from({ length: n }, (_, i) => i + 1)

// 2026 kWh je Monat = 300, 2025 = 200 → die Summen sind auseinanderzuhalten.
const KWH = { 2026: 300, 2025: 200 } as Record<number, number>

const zeile = (jahr: number, monat: number) =>
  monatsZeile(jahr, monat, {
    pv_erzeugung_kwh: KWH[jahr], eigenverbrauch_kwh: KWH[jahr] / 2, direktverbrauch_kwh: KWH[jahr] / 4,
    einspeisung_kwh: KWH[jahr] / 2, netzbezug_kwh: 50, gesamtverbrauch_kwh: KWH[jahr] / 2 + 50,
  })

// Aggregat-Liste: 2026 nur Jan–Jun (Juli ist nicht abgeschlossen), 2025 voll.
const aggregiert: AggregierteMonatsdaten[] = [
  ...bis(6).map((m) => zeile(2026, m)),
  ...bis(12).map((m) => zeile(2025, m)),
]

/** Monate MIT gemessenen Daten — 2026 bis August, 2025 voll. Veränderbar, damit
 *  ein Test einen gefragten, aber leeren Monat nachstellen kann. */
let hatDaten = new Set<string>()
const HAT_DATEN_STANDARD = [
  ...bis(8).map((m) => `2026-${m}`),
  ...bis(12).map((m) => `2025-${m}`),
]

/** Antwort für einen Monat vor der Inbetriebnahme: nur Stammdaten-Ableitungen. */
const ohneDaten = (jahr: number, monat: number): AktuellerMonatResponse =>
  aktuellerMonat(jahr, monat, {
    anlage_name: 'Demo', monat_name: String(monat),
    soll_pv_kwh: 400, netzbezug_preis_cent: 40, einspeise_preis_cent: 8.2,
  })

/** SOLL ist standardmäßig aus: sonst belegt die SOLL-Annotation die PV-Zweitzeile
 *  und die Vorjahres-Angabe wäre dort nicht ablesbar. Ein Test schaltet es an. */
let sollAktiv = false

const mitDaten = (jahr: number, monat: number): AktuellerMonatResponse => ({
  ...ohneDaten(jahr, monat),
  soll_pv_kwh: sollAktiv ? 250 : null,
  pv_erzeugung_kwh: KWH[jahr], einspeisung_kwh: KWH[jahr] / 2, netzbezug_kwh: 50,
  eigenverbrauch_kwh: KWH[jahr] / 2, direktverbrauch_kwh: KWH[jahr] / 4,
  gesamtverbrauch_kwh: KWH[jahr] / 2 + 50,
  autarkie_prozent: 75, eigenverbrauch_quote_prozent: 50,
})

const getData = vi.fn((_id: number, j: number, m: number) =>
  Promise.resolve(hatDaten.has(`${j}-${m}`) ? mitDaten(j, m) : ohneDaten(j, m)))

vi.mock('../api/monatsdaten', () => ({
  monatsdatenApi: { listAggregiert: vi.fn(() => Promise.resolve(aggregiert)) },
}))
vi.mock('../api/aktuellerMonat', () => ({
  aktuellerMonatApi: { getData: (...a: [number, number, number]) => getData(...a) },
}))
const leereNachhaltigkeit: Nachhaltigkeit = {
  anlage_id: 1, co2_gesamt_kg: 0, co2_pv_kg: 0, co2_wp_kg: 0, co2_emob_kg: 0,
  aequivalent_baeume: 0, aequivalent_auto_km: 0, aequivalent_fluege_km: 0,
  autarkie_durchschnitt_prozent: 0, monatswerte: [],
}
vi.mock('../api/cockpit', () => ({
  cockpitApi: { getNachhaltigkeit: vi.fn(() => Promise.resolve(leereNachhaltigkeit)) },
}))

import CockpitJahrV4 from './CockpitJahrV4'

function renderView() {
  return renderMitProvidern(<CockpitJahrV4 anlageId={1} />)
}

async function oeffneBilanz() {
  const titel = await screen.findByText('Energie-Bilanz')
  fireEvent.click(titel.closest('button')!)
}

describe('Cockpit/Jahr — laufendes Jahr mit unabgeschlossenem Monat (N-65)', () => {
  beforeEach(() => {
    localStorage.clear()
    getData.mockClear()
    hatDaten = new Set(HAT_DATEN_STANDARD)
    sollAktiv = false
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(new Date(2026, 7, 2, 12, 0, 0))
    stubMatchMedia()
  })
  afterEach(() => { vi.useRealTimers() })

  it('die Kopfzahl trägt den Monat OHNE Aggregat-Zeile', async () => {
    renderView()
    const karte = (await screen.findByText('PV-Erzeugung')).closest('div')!
    // Jan–Aug × 300 kWh = 2.400. Bis v4.0.6 waren es 2.100 (Jan–Jun + Aug):
    // der volle Juli fehlte, der angefangene August war drin.
    expect(within(karte).getByText('2.400')).toBeInTheDocument()
    // Juli wurde wirklich gefragt, obwohl er keine Zeile hat.
    expect(getData.mock.calls.filter((c) => c[1] === 2026).map((c) => c[2])).toEqual(bis(8))
  })

  it('die Block-Kopfzeile nennt das Fenster der Kacheln', async () => {
    // NICHT die Kachel-Zweitzeile: die ist `truncate` und fasst rund 22 Zeichen —
    // ein Präfix dort schnitt an der Box genau die Vorjahres-Angabe ab, die es
    // einordnen sollte. Die Kopfzeile darüber rendert ungekürzt.
    renderView()
    await screen.findByText('PV-Erzeugung')
    expect(screen.getByText(
      'Jan–Aug · 5 Energie-Kennzahlen + Netto-Ertrag + Jahresergebnis + Netz-Kosten',
    )).toBeInTheDocument()
    // Die Zweitzeile bleibt, was sie war — Vorjahr Jan–Jul × 200 kWh = 1.400.
    expect(screen.getByText('VJ (Jan–Jul): 1.400 kWh')).toBeInTheDocument()
  })

  it('die Vergleichstabelle rechnet BEIDE Seiten über Jan–Jul', async () => {
    renderView()
    await oeffneBilanz()
    const zeilen = screen.getAllByRole('row')
    const pv = zeilen.find((r) => within(r).queryByText('PV-Erzeugung'))!
    // IST = 7 × 300 = 2.100 (nicht 2.400 — der laufende August gehört nicht in
    // einen Vergleich), Vorjahr = 7 × 200 = 1.400.
    expect(within(pv).getByText('2.100')).toBeInTheDocument()
    // Zweimal 1.400: Vorjahr-Spalte und Ø-Jahre-Spalte (hier dasselbe eine Jahr).
    expect(within(pv).getAllByText('1.400').length).toBeGreaterThanOrEqual(1)
  })

  it('die SOLL-Erfüllung bleibt EINE Zahl — an der Kachel, nicht auch im Block-Kopf', async () => {
    // Über Jan–Jul gerechnet ergäbe der Block-Kopf eine zweite, andere Prozentzahl
    // für dieselbe Größe (an der Box 119 % gegen 103 %). Der Unterschied ist echt —
    // der laufende Monat bringt sein volles PVGIS-SOLL mit —, gehört aber an eine
    // Stelle und ist ein eigener Fund.
    sollAktiv = true
    renderView()
    await screen.findByText('PV-Erzeugung')
    expect(screen.getByText(/^Jan–Jul · 2\.100 kWh PV/)).toBeInTheDocument()
    expect(screen.queryByText(/Jan–Jul · .*SOLL/)).not.toBeInTheDocument()
    // An der Kachel steht sie: 8 × 300 ÷ (8 × 250) = 120 %.
    expect(screen.getByText('SOLL 2.000 kWh · 120 %')).toBeInTheDocument()
  })

  it('der Unterschied zwischen Kachel und Tabelle steht im Fuß', async () => {
    renderView()
    await oeffneBilanz()
    expect(screen.getByText(
      /Vergleich beschnitten auf die gemeinsamen Monate: Jan–Jul · Kennzahlen oben: Jan–Aug/,
    )).toBeInTheDocument()
    // Und über der IST-Spalte selbst (Desktop-Kopfzeile): IST + Vorjahr + Ø Jahre.
    expect(screen.getAllByText('Jan–Jul').length).toBeGreaterThanOrEqual(2)
  })

  it('ein gefragter, aber leerer Monat zählt NICHT mit', async () => {
    // Juli antwortet ohne Mengen (nur SOLL + Tarif) — genau die Antwort, die die Box
    // für Monate vor der Inbetriebnahme gibt. Er darf weder in die Kopfzahl noch in
    // die Grundgesamtheit, sonst bliese er das SOLL auf.
    hatDaten.delete('2026-7')
    renderView()
    const karte = (await screen.findByText('PV-Erzeugung')).closest('div')!
    // Jan–Jun + Aug = 7 × 300 = 2.100, und das Fenster hat die Lücke.
    expect(within(karte).getByText('2.100')).toBeInTheDocument()
    expect(screen.getByText(/^Jan–Jun, Aug · 5 Energie-Kennzahlen/)).toBeInTheDocument()
  })
})

describe('Cockpit/Jahr — REGRESSION: abgeschlossenes Jahr unverändert', () => {
  beforeEach(() => {
    localStorage.clear()
    getData.mockClear()
    hatDaten = new Set(HAT_DATEN_STANDARD)
    sollAktiv = false
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(new Date(2026, 7, 2, 12, 0, 0))
    stubMatchMedia()
  })
  afterEach(() => { vi.useRealTimers() })

  it('2025: Kopfzahl und Tabelle decken sich, keine Zusatzbeschriftung', async () => {
    renderView()
    await screen.findByText('Kennzahlen')
    fireEvent.click(screen.getAllByText('2025')[0])
    await oeffneBilanz()

    // 12 × 200 = 2.400 — Kachel und IST-Spalte dieselbe Zahl.
    expect(screen.getAllByText('2.400').length).toBeGreaterThanOrEqual(2)
    // Kein Fenster: weder an der Kachel noch über der Spalte noch im Fuß.
    expect(screen.queryByText(/IST Jan–/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Kennzahlen oben/)).not.toBeInTheDocument()
    expect(screen.queryByText(/beschnitten/)).not.toBeInTheDocument()
    // Und genau zwölf Requests, kein Mehraufwand für vergangene Jahre.
    expect(getData.mock.calls.filter((c) => c[1] === 2025)).toHaveLength(12)
    // Die Block-Kopfzeilen tragen kein Fenster — und der Bilanz-Kopf behält sein SOLL.
    expect(screen.getByText('5 Energie-Kennzahlen + Netto-Ertrag + Jahresergebnis + Netz-Kosten'))
      .toBeInTheDocument()
  })
})
