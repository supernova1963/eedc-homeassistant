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
 * feste Systemzeit.
 *
 * ⭐ Seit 03.10.2026 entscheidet die **Jahresroute** (Backend), welche Monate gefragt werden
 * und welche zählen (`zu_ladende_monate`, `monat_hat_daten`, `abgeschlossene_monate`) — die
 * Proben dazu stehen mit denselben Zahlen in `backend/tests/test_ergebnis_jahr_portiert.py`.
 * Hier bleibt, was die SICHT mit der Antwort tut: Kachel = Kopf (Jan–Aug), Tabelle =
 * Vergleich (Jan–Jul) auf beiden Seiten, Fenster und Grund an Kachel, Spalte und Fuß.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, fireEvent, within } from '@testing-library/react'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'
import type { Nachhaltigkeit } from '../api/cockpit'
import { cockpitJahr, jahrVergleich, monatsZeile } from '../test/factories'
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

/** SOLL ist standardmäßig aus: sonst belegt die SOLL-Annotation die PV-Zweitzeile
 *  und die Vorjahres-Angabe wäre dort nicht ablesbar. Ein Test schaltet es an. */
let sollAktiv = false
/** Juli ohne Mengen (die Antwort der Box für einen Monat vor der Inbetriebnahme) — die Route lässt ihn weg. */
let juliLeer = false

/** Σ über n Monate des Jahres 2026 (je 300 kWh PV, 150 EV, 75 Direkt, 150 Einspeisung, 50 Netz, 200 GV). */
const summe2026 = (n: number) => ({
  anlage_name: 'Demo',
  pv_erzeugung_kwh: 300 * n, einspeisung_kwh: 150 * n, netzbezug_kwh: 50 * n,
  eigenverbrauch_kwh: 150 * n, direktverbrauch_kwh: 75 * n, gesamtverbrauch_kwh: 200 * n,
  autarkie_prozent: 75, eigenverbrauch_quote_prozent: 50,
})

/** Die Jahresroute für 2026 am 02.08.: Kopf Jan–Aug, Vergleich Jan–Jul, Vorjahr 2025 über Jan–Jul (7 × 200 kWh). */
function jahr2026() {
  const kopfMonate = juliLeer ? [1, 2, 3, 4, 5, 6, 8] : bis(8)
  const vglMonate = kopfMonate.filter((m) => m < 8)
  const vj = jahrVergleich(2025, {
    pv: 200 * vglMonate.length, ev: 100 * vglMonate.length, direkt: 50 * vglMonate.length,
    einsp: 100 * vglMonate.length, netz: 50 * vglMonate.length, gesamt: 150 * vglMonate.length,
    autarkie: (100 / 150) * 100, monate: vglMonate,
  })
  return cockpitJahr(2026, {
    monate_nr: kopfMonate,
    vergleichs_monate: vglMonate,
    kopf: {
      ...summe2026(kopfMonate.length),
      // SOLL an: 8 × 250 = 2.000 kWh, Quote 8 × 300 ÷ 2.000 = 120 % (aus der Antwort, N-356).
      soll_pv_kwh: sollAktiv ? 250 * kopfMonate.length : null,
      soll_erfuellung_prozent: sollAktiv ? 120 : null,
    },
    vergleich: {
      ...summe2026(vglMonate.length),
      soll_pv_kwh: sollAktiv ? 250 * vglMonate.length : null,
      soll_erfuellung_prozent: sollAktiv ? 120 : null,
    },
    vorjahr: vj,
    oe_jahr: { ...vj, jahr: 0, count: 1 },
  })
}

/** 2025 abgeschlossen: Kopf = Vergleich = 12 × 200 kWh; kein Vorjahr (2024 ohne Daten), kein Ø (2026 deckt nicht). */
const jahr2025 = () => cockpitJahr(2025, {
  monate_nr: bis(12),
  kopf: {
    anlage_name: 'Demo', pv_erzeugung_kwh: 2400, einspeisung_kwh: 1200, netzbezug_kwh: 600,
    eigenverbrauch_kwh: 1200, direktverbrauch_kwh: 600, gesamtverbrauch_kwh: 1800,
    autarkie_prozent: (1200 / 1800) * 100, eigenverbrauch_quote_prozent: 50,
  },
})

const getJahr = vi.fn((_id: number, j: number) => Promise.resolve(j === 2025 ? jahr2025() : jahr2026()))

vi.mock('../api/monatsdaten', () => ({
  monatsdatenApi: { listAggregiert: vi.fn(() => Promise.resolve(aggregiert)) },
}))
vi.mock('../api/aktuellerMonat', () => ({
  aktuellerMonatApi: { getData: vi.fn(() => Promise.reject(new Error('Cockpit → Jahr lädt keine Einzelmonate mehr'))) },
}))
const leereNachhaltigkeit: Nachhaltigkeit = {
  anlage_id: 1, co2_gesamt_kg: 0, co2_pv_kg: 0, co2_wp_kg: 0, co2_emob_kg: 0,
  aequivalent_baeume: 0, aequivalent_auto_km: 0, aequivalent_fluege_km: 0,
  autarkie_durchschnitt_prozent: 0, monatswerte: [],
}
vi.mock('../api/cockpit', () => ({
  cockpitApi: {
    getNachhaltigkeit: vi.fn(() => Promise.resolve(leereNachhaltigkeit)),
    getJahr: (...a: [number, number]) => getJahr(...a),
  },
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
    getJahr.mockClear()
    juliLeer = false
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
    // EIN Abruf für das Jahr — dass die Route den Juli ohne Zeile mitfragt, prüft
    // `test_ergebnis_jahr_portiert.py::test_menge_luecke_bis_heute` (dieselbe Lage).
    expect(getJahr.mock.calls.filter((c) => c[1] === 2026)).toHaveLength(1)
  })

  it('die Block-Kopfzeile nennt das Fenster der Kacheln — und warum es weiter reicht', async () => {
    // NICHT die Kachel-Zweitzeile: die ist `truncate` und fasst rund 22 Zeichen —
    // ein Präfix dort schnitt an der Box genau die Vorjahres-Angabe ab, die es
    // einordnen sollte. Die Kopfzeile darüber hat mehr Platz.
    // ⚠ Hier stand bis 31.08.2026 „Die Kopfzeile darüber rendert ungekürzt." Das ist
    // falsch und an der Box widerlegt: `BlockShell` gibt der Summary `truncate` und
    // ein starkes `flex-shrink`; bei 390 px Breite blieb „5 Energie-Ken…" übrig.
    // Sie hat MEHR Platz, nicht unbegrenzten — deshalb steht das Fenster VORN.
    renderView()
    await screen.findByText('PV-Erzeugung')
    // „(bis heute)" seit T89667 #276 (Burkard): Der Zeitraum allein reichte nicht —
    // er las 9.860 kWh über 8.428 kWh, beide richtig, und hielt es für einen
    // Widerspruch, weil nirgends stand, WARUM die Fenster verschieden weit reichen.
    expect(screen.getByText(
      'Jan–Aug (bis heute) · 5 Energie-Kennzahlen + Netto-Ertrag + Jahresergebnis + Netz-Kosten',
    )).toBeInTheDocument()
    // Die Gegenrichtung am selben Bildschirm: der Bilanz-Kopf sagt „abgeschlossen".
    expect(screen.getByText(/^Jan–Jul \(abgeschlossen\) · 2\.100 kWh PV/)).toBeInTheDocument()
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
    expect(screen.getByText(/^Jan–Jul \(abgeschlossen\) · 2\.100 kWh PV/)).toBeInTheDocument()
    // ⚠ Der Zusatz „(abgeschlossen)" MUSS auch hier stehen: Ohne ihn wäre die
    // Negativ-Zusicherung darunter seit dem 31.08. leer erfüllt — sie suchte
    // `Jan–Jul · …SOLL`, und diese Form gibt es im Kopf gar nicht mehr. Eine Probe,
    // die nichts mehr treffen KANN, ist grün und wertlos.
    expect(screen.queryByText(/Jan–Jul \(abgeschlossen\) · .*SOLL/)).not.toBeInTheDocument()
    // An der Kachel steht sie: 8 × 300 ÷ (8 × 250) = 120 %.
    expect(screen.getByText('SOLL 2.000 kWh · 120 %')).toBeInTheDocument()
  })

  it('der Unterschied zwischen Kachel und Tabelle steht im Fuß — samt Grund', async () => {
    renderView()
    await oeffneBilanz()
    expect(screen.getByText(
      /Vergleich beschnitten auf die gemeinsamen Monate: Jan–Jul · Kennzahlen oben: Jan–Aug/,
    )).toBeInTheDocument()
    // Die Kopfzeilen tragen die Kurzform, hier ist Platz für den ganzen Satz — und
    // der ist es, der den Widerspruch auflöst statt ihn nur zu beschriften.
    expect(screen.getByText(
      /Kennzahlen oben: Jan–Aug — sie zählen jeden Monat mit Daten, also auch den laufenden\./,
    )).toBeInTheDocument()
    expect(screen.getByText(
      /Diese Tabelle rechnet nur über die abgeschlossenen Monate/,
    )).toBeInTheDocument()
    // Und über der IST-Spalte selbst (Desktop-Kopfzeile): IST + Vorjahr + Ø Jahre.
    expect(screen.getAllByText('Jan–Jul').length).toBeGreaterThanOrEqual(2)
  })

  it('ein gefragter, aber leerer Monat zählt NICHT mit', async () => {
    // Juli antwortet ohne Mengen (nur SOLL + Tarif) — genau die Antwort, die die Box
    // für Monate vor der Inbetriebnahme gibt. Er darf weder in die Kopfzahl noch in
    // die Grundgesamtheit, sonst bliese er das SOLL auf.
    juliLeer = true
    renderView()
    const karte = (await screen.findByText('PV-Erzeugung')).closest('div')!
    // Jan–Jun + Aug = 7 × 300 = 2.100, und das Fenster hat die Lücke.
    expect(within(karte).getByText('2.100')).toBeInTheDocument()
    expect(screen.getByText(/^Jan–Jun, Aug \(bis heute\) · 5 Energie-Kennzahlen/)).toBeInTheDocument()
  })
})

describe('Cockpit/Jahr — REGRESSION: abgeschlossenes Jahr unverändert', () => {
  beforeEach(() => {
    localStorage.clear()
    getJahr.mockClear()
    juliLeer = false
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
    // EIN Abruf je Jahr (bis 03.10.2026: zwölf Monats-Requests).
    expect(getJahr.mock.calls.filter((c) => c[1] === 2025)).toHaveLength(1)
    // Die Block-Kopfzeilen tragen kein Fenster — und der Bilanz-Kopf behält sein SOLL.
    expect(screen.getByText('5 Energie-Kennzahlen + Netto-Ertrag + Jahresergebnis + Netz-Kosten'))
      .toBeInTheDocument()
    // Und die Gegenprobe zum Zusatz aus T89667 #276: Wo sich die beiden Zeiträume
    // DECKEN, gibt es nichts zu unterscheiden — dann wäre „(bis heute)" bzw.
    // „(abgeschlossen)" nur Rauschen. Der Zusatz hängt deshalb an
    // `kennzahlenFenster != null`, nicht am Vorhandensein eines Fensters.
    expect(screen.queryByText(/\(bis heute\)/)).not.toBeInTheDocument()
    expect(screen.queryByText(/\(abgeschlossen\)/)).not.toBeInTheDocument()
  })
})
