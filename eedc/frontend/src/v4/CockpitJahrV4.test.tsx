/**
 * CockpitJahrV4 — Struktur-Smoke-Test: Jahr als Monat-Variante.
 * Sichert: Jahres-Auswahl-Kopf (Status-Badge + Rail/Stepper) + die Monat-Block-
 * Reihe auf Jahresebene (Kennzahlen / Energie-Bilanz / Verlauf / CO₂-Bilanz /
 * Komponenten / Finanzen), gespeist aus Σ der Monats-Antworten + der aggregierten
 * Monatsreihe + der CO₂-Zeitreihe.
 *
 * jsdom-Grenze (bekannt): Recharts misst seinen Container über `ResponsiveContainer`
 * und rendert in jsdom deshalb KEINE Balken. Geprüft wird darum die
 * **Datenaufbereitung** (reine Funktionen) und die **Struktur** (Block, Parkbar,
 * Tabellen-Spalten) — keine Pixel.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../context/ThemeContext'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'
import type { Nachhaltigkeit, NachhaltigkeitMonat } from '../api/cockpit'

// Zwei vergangene Jahre (2024/2025) → Default = neuestes mit Daten = 2025
// (≠ aktuelles Jahr → „abgeschlossen", kein Reload-Button — wie Monat).
const monatsZeile = (jahr: number, monat: number): AggregierteMonatsdaten => ({
  jahr, monat,
  pv_erzeugung_kwh: 300, eigenverbrauch_kwh: 180, einspeisung_kwh: 120,
  netzbezug_kwh: 90, direktverbrauch_kwh: 140, gesamtverbrauch_kwh: 270,
  autarkie_prozent: 66, speicher_entladung_kwh: 40,
} as unknown as AggregierteMonatsdaten)

const aggregiert: AggregierteMonatsdaten[] = [
  ...[1, 2, 3].map((m) => monatsZeile(2025, m)),
  ...[1, 2].map((m) => monatsZeile(2024, m)),
]

const monatsAntwort = (jahr: number, monat: number): AktuellerMonatResponse => ({
  anlage_id: 1, anlage_name: 'Demo', jahr, monat, monat_name: String(monat),
  aktualisiert_um: '', quellen: {},
  pv_erzeugung_kwh: 300, einspeisung_kwh: 120, netzbezug_kwh: 90,
  eigenverbrauch_kwh: 180, direktverbrauch_kwh: 140, gesamtverbrauch_kwh: 270,
  autarkie_prozent: 66, eigenverbrauch_quote_prozent: 60,
  speicher_ladung_kwh: 50, speicher_entladung_kwh: 43, speicher_wirkungsgrad_prozent: 86,
  speicher_vollzyklen: 4, speicher_kapazitaet_kwh: 10, hat_speicher: true,
  speicher_soc_drift_signifikant: false,
  wp_strom_kwh: 60, wp_waerme_kwh: 180, wp_heizung_kwh: 140, wp_warmwasser_kwh: 40,
  hat_waermepumpe: true,
  einspeise_erloes_euro: 12, netzbezug_kosten_euro: 27, ev_ersparnis_euro: 50,
  netto_ertrag_euro: 35, gesamtnettoertrag_euro: 35, betriebskosten_anteilig_euro: 5,
  sonstige_netto_euro: 0, sonstige_ertraege_euro: 0, sonstige_ausgaben_euro: 0,
  soll_pv_kwh: 320,
  investitionen_financials: [], komponenten_geraete: {}, feld_quellen: {},
  vorjahr: null,
} as unknown as AktuellerMonatResponse)

vi.mock('../api/monatsdaten', () => ({
  monatsdatenApi: { listAggregiert: vi.fn(() => Promise.resolve(aggregiert)) },
}))

vi.mock('../api/aktuellerMonat', () => ({
  aktuellerMonatApi: { getData: vi.fn((_id: number, j: number, m: number) => Promise.resolve(monatsAntwort(j, m))) },
}))

// CO₂-Zeitreihe: der Endpoint liefert die GANZE Historie ohne `?jahr=` — die
// Fixture trägt deshalb bewusst zwei Jahre, damit der Frontend-Filter etwas zu
// filtern hat. `co2_kumuliert_kg` läuft über beide Jahre durch (Lebensdauer-Zahl).
const co2Monat = (jahr: number, monat: number, pv: number, kumuliert: number): NachhaltigkeitMonat => ({
  jahr, monat, monat_name: String(monat),
  co2_pv_kg: pv, co2_wp_kg: 20, co2_emob_kg: 10,
  co2_gesamt_kg: pv + 30, co2_kumuliert_kg: kumuliert,
  autarkie_prozent: 66,
})

const nachhaltigkeit: Nachhaltigkeit = {
  anlage_id: 1, co2_gesamt_kg: 1000, co2_pv_kg: 700, co2_wp_kg: 200, co2_emob_kg: 100,
  aequivalent_baeume: 50, aequivalent_auto_km: 8000, aequivalent_fluege_km: 4000,
  autarkie_durchschnitt_prozent: 66,
  monatswerte: [
    co2Monat(2024, 11, 100, 130),
    co2Monat(2024, 12, 100, 260),
    co2Monat(2025, 1, 100, 390),
    co2Monat(2025, 2, 200, 620),
    co2Monat(2025, 3, 300, 950),
  ],
}

vi.mock('../api/cockpit', () => ({
  cockpitApi: { getNachhaltigkeit: vi.fn(() => Promise.resolve(nachhaltigkeit)) },
}))

import CockpitJahrV4 from './CockpitJahrV4'
import { baueJahrCo2ChartDaten, co2JahresSumme, CO2_TABELLEN_SPALTEN } from './JahrCo2Chart'

// CockpitJahrV4 rendert JahrVerlaufChart, das seit B3 useNavigate nutzt → Router nötig.
function renderView() {
  return render(
    <MemoryRouter>
      <ThemeProvider>
        <CockpitJahrV4 anlageId={1} />
      </ThemeProvider>
    </MemoryRouter>,
  )
}

describe('CockpitJahrV4 — Jahr', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: false, media: '', onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }))
  })

  it('zeigt Jahres-Kopf (Status-Badge) + Auswahl (Rail/Stepper)', async () => {
    renderView()
    expect(await screen.findByText('abgeschlossen')).toBeInTheDocument()
    expect(screen.getAllByText('2025').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'voriges Jahr' })).toBeInTheDocument()
  })

  it('rendert die Monat-Block-Reihe auf Jahresebene (inkl. Komponenten + Finanzen)', async () => {
    renderView()
    expect(await screen.findByText('Kennzahlen')).toBeInTheDocument()
    expect(screen.getByText('Energie-Bilanz')).toBeInTheDocument()
    expect(screen.getByText('Verlauf')).toBeInTheDocument()
    expect(screen.getByText('CO₂-Bilanz')).toBeInTheDocument()
    expect(screen.getByText('Speicher')).toBeInTheDocument()
    expect(screen.getByText('Wärme/Klima')).toBeInTheDocument()
    expect(screen.getByText('Finanzen')).toBeInTheDocument()
  })

  it('beschneidet Vorjahr/Ø-Jahr auf die Monate des angezeigten Jahres und sagt es (N-37)', async () => {
    // Fixture: 2025 hat Jan–Mär, 2024 nur Jan–Feb ⇒ Überschneidung = Jan–Feb.
    // Vorher summierte die Vergleichsspalte das ganze Jahr 2024.
    renderView()
    const titel = await screen.findByText('Energie-Bilanz')
    fireEvent.click(titel.closest('button')!)
    expect(screen.getByText(/Vergleich beschnitten auf die gemeinsamen Monate: Jan–Feb/))
      .toBeInTheDocument()
    // Dieselbe Angabe an der Kachel (Einspeisung: 2 × 120 kWh aus 2024).
    expect(screen.getByText('VJ (Jan–Feb): 240 kWh')).toBeInTheDocument()
  })
})

// ─── CO₂-Bilanz (Nebenfunde-Paket B') ────────────────────────────────────────

describe('CockpitJahrV4 — CO₂-Zeitreihe: Datenaufbereitung', () => {
  it('filtert auf das gewählte Jahr — und zwar die GANZE Zeile, nicht einzelne Serien', () => {
    const punkte = baueJahrCo2ChartDaten(nachhaltigkeit.monatswerte, 2025)
    expect(punkte).toHaveLength(3)
    expect(punkte.map((p) => p.monatNr)).toEqual([1, 2, 3])
    // Jede Serie stammt aus derselben gefilterten Zeile: kein Rest aus 2024.
    expect(punkte.map((p) => p.co2Pv)).toEqual([100, 200, 300])
    expect(punkte.map((p) => p.co2Wp)).toEqual([20, 20, 20])
    expect(punkte.map((p) => p.co2Emob)).toEqual([10, 10, 10])
    expect(punkte.map((p) => p.autarkie)).toEqual([66, 66, 66])
  })

  it('sortiert aufsteigend nach Monat und beschriftet mit dem Kurznamen', () => {
    const gemischt = [nachhaltigkeit.monatswerte[4], nachhaltigkeit.monatswerte[2], nachhaltigkeit.monatswerte[3]]
    expect(baueJahrCo2ChartDaten(gemischt, 2025).map((p) => p.monat)).toEqual(['Jan', 'Feb', 'Mär'])
  })

  it('nimmt die Stapel-Höhe aus dem Backend-Kanon statt sie nachzurechnen', () => {
    // `co2_gesamt_kg` ist im Backend die Summe der GEKLEMMTEN Anteile — hier wird
    // sie durchgereicht, damit Balkenhöhe und Kennwert dieselbe Zahl sind.
    expect(baueJahrCo2ChartDaten(nachhaltigkeit.monatswerte, 2025).map((p) => p.co2Gesamt))
      .toEqual([130, 230, 330])
  })

  it('leeres Jahr → leere Reihe (kein Absturz, kein Fremdjahr)', () => {
    expect(baueJahrCo2ChartDaten(nachhaltigkeit.monatswerte, 2023)).toEqual([])
  })

  it('co2JahresSumme summiert NUR das gewählte Jahr', () => {
    expect(co2JahresSumme(baueJahrCo2ChartDaten(nachhaltigkeit.monatswerte, 2025))).toBe(690)
    expect(co2JahresSumme(baueJahrCo2ChartDaten(nachhaltigkeit.monatswerte, 2024))).toBe(260)
  })

  it('Tabellen-Spalten = Union der Chart-Serien (+ Stapel-Höhe), kg summierbar', () => {
    expect(CO2_TABELLEN_SPALTEN.map((s) => s.key))
      .toEqual(['co2Pv', 'co2Wp', 'co2Emob', 'co2Gesamt', 'autarkie'])
    // Jede Spalte existiert wirklich in der Chart-Datenreihe (Regel D: 1:1-Ablesung).
    const punkt = baueJahrCo2ChartDaten(nachhaltigkeit.monatswerte, 2025)[0] as unknown as Record<string, unknown>
    for (const s of CO2_TABELLEN_SPALTEN) expect(punkt).toHaveProperty(s.key)
    // `kg` steht nicht in der Summierbar-Default-Menge → muss explizit gesetzt sein.
    for (const s of CO2_TABELLEN_SPALTEN.filter((s) => s.einheit === 'kg')) {
      expect(s.summierbar).toBe(true)
    }
  })
})

describe('CockpitJahrV4 — CO₂-Block', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: false, media: '', onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }))
  })

  it('nennt in der Kopfzeile Jahres-Summe UND kumulierte Lebensdauer-Zahl', async () => {
    renderView()
    await screen.findByText('CO₂-Bilanz')
    // 690 kg = Σ 2025; 950 kg = letzter Kumuliert-Wert der GESAMTEN Historie
    // (nicht der des Jahres — sonst stünde hier 330).
    expect(screen.getByText('690 kg eingespart · kumuliert 950 kg')).toBeInTheDocument()
  })

  it('aufgeklappt: beide Kennwerte + die parkbare Chart-Anzeige', async () => {
    const { container } = renderView()
    const titel = await screen.findByText('CO₂-Bilanz')
    fireEvent.click(titel.closest('button')!)

    expect(screen.getByText('CO₂ eingespart')).toBeInTheDocument()
    expect(screen.getByText('CO₂ kumuliert')).toBeInTheDocument()
    // Der Zeitbezug steht am Kennwert, nicht nur im Code-Kommentar.
    expect(screen.getByText('gesamte Historie — nicht jahresgebunden')).toBeInTheDocument()
    expect(screen.getByText('2025 · PV + Wärmepumpe + E-Mobilität')).toBeInTheDocument()

    // Park-Doktrin: EINE Parkbar um GENAU EINE Anzeige (den Chart). Recharts selbst
    // rendert in jsdom nicht — geprüft wird die Umhüllung, nicht das Bild.
    expect(container.querySelector('[data-park-id="el:co2"]')).not.toBeNull()
    expect(screen.getByText(/Gestapelt: PV\/Eigenverbrauch/)).toBeInTheDocument()
  })
})
