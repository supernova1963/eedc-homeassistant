/**
 * Cockpit → Jahr zeigt EINE Periode — dieselbe Regel wie in Tag und Monat.
 *
 * ⚠ **Hier hängt die Mischung nicht an einer zweiten Abfrage.** Die CO₂-Reihe
 * kommt aus EINEM Abruf über die ganze Historie, die Monatsbalken und die
 * Vergleiche aus der aggregierten Monatsliste — beide sind **immer** geladen.
 * Sie sprangen deshalb ohne jede Ladezeit auf das neue Jahr, während die Kacheln
 * daneben noch das alte zeigten: dieselbe Klasse, nur über einen Client-Filter
 * statt über eine Antwortzeit.
 *
 * Fünf Proben, je eine Klausel: Paarung · Vorhalt · Kopf · Nachlauf ·
 * Zählerstände. Aufbau: der Abruf der Jahresroute für das Ziel-Jahr wird angehalten
 * (damit hängt `jahrQ` als Ganzes), alles andere antwortet sofort. Bis 03.10.2026
 * hingen hier die zwölf Monats-Abrufe — seit der Jahresroute ist es EIN Abruf.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, act } from '@testing-library/react'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'
import type { Nachhaltigkeit, NachhaltigkeitMonat } from '../api/cockpit'
import type { ZaehlerStand } from '../api/zaehlerstaende'

// Angezeigt wird 2025 (Default = neuestes Jahr mit Daten), geblättert wird auf 2024.
const NEU = 2024   // das gewählte Jahr, dessen Monats-Abrufe hängen

/** Einzelwerte je Jahr, an denen im DOM zu erkennen ist, wer gerade spricht. */
const PV_JE_MONAT: Record<number, number> = { 2025: 300, 2024: 100 }
const MONATE_JE_JAHR: Record<number, number[]> = { 2025: [1, 2, 3], 2024: [1, 2] }
/** PV-Jahressumme: 2025 → 900 · 2024 → 200. */
const CO2_PV_JE_MONAT: Record<number, number> = { 2025: 100, 2024: 40 }
/** CO₂-Jahressumme (co2_gesamt = pv + 30 je Monat): 2025 → 390 · 2024 → 140. */
const ZAEHLER_ENDE: Record<number, number> = { 2025: 1234, 2024: 5678 }

const H = vi.hoisted(() => ({
  wartend: new Map<string, () => void>(),
  /** Für diese Jahre antwortet die Jahresroute erst auf Zuruf. */
  angehalten: new Set<number>(),
}))

import { aktuellerMonat, cockpitJahr, monatsZeile } from '../test/factories'
import { renderMitProvidern, stubMatchMedia } from '../test/render'
import { _clearSwrCacheForTests } from '../hooks/useApiData'

const aggregiert: AggregierteMonatsdaten[] = [2025, 2024].flatMap((j) =>
  MONATE_JE_JAHR[j].map((m) => monatsZeile(j, m, {
    pv_erzeugung_kwh: PV_JE_MONAT[j], eigenverbrauch_kwh: 180, einspeisung_kwh: 120,
    netzbezug_kwh: 90, direktverbrauch_kwh: 140, gesamtverbrauch_kwh: 270,
    autarkie_prozent: 66,
  })),
)

const MIT_DATEN = new Set(aggregiert.map((m) => `${m.jahr}-${m.monat}`))

function monatsAntwort(jahr: number, monat: number) {
  return aktuellerMonat(jahr, monat, {
    anlage_name: 'Demo', monat_name: String(monat),
    pv_erzeugung_kwh: MIT_DATEN.has(`${jahr}-${monat}`) ? PV_JE_MONAT[jahr] : 0,
    einspeisung_kwh: 120, netzbezug_kwh: 90, eigenverbrauch_kwh: 180,
    direktverbrauch_kwh: 140, gesamtverbrauch_kwh: 270, autarkie_prozent: 66,
    eigenverbrauch_quote_prozent: 60,
    netto_ertrag_euro: 35,
  })
}

const co2Monat = (jahr: number, monat: number): NachhaltigkeitMonat => ({
  jahr, monat, monat_name: String(monat),
  co2_pv_kg: CO2_PV_JE_MONAT[jahr], co2_wp_kg: 20, co2_emob_kg: 10,
  co2_gesamt_kg: CO2_PV_JE_MONAT[jahr] + 30, co2_kumuliert_kg: 1000,
  autarkie_prozent: 66,
})

const nachhaltigkeit: Nachhaltigkeit = {
  anlage_id: 1, co2_gesamt_kg: 1000, co2_pv_kg: 700, co2_wp_kg: 200, co2_emob_kg: 100,
  aequivalent_baeume: 50, aequivalent_auto_km: 8000, aequivalent_fluege_km: 4000,
  autarkie_durchschnitt_prozent: 66,
  monatswerte: [2024, 2025].flatMap((j) => MONATE_JE_JAHR[j].map((m) => co2Monat(j, m))),
}

function zaehlerStand(jahr: number): ZaehlerStand {
  const ende = ZAEHLER_ENDE[jahr] ?? 0
  return {
    investition_id: 1, name: 'Gaszähler', art: 'gas', einheit: 'm³',
    stand_anfang: 1000, stand_ende: ende, differenz: ende - 1000,
    anfang_vollstaendig: true, rueckwaerts: false, verlauf: [],
  } as unknown as ZaehlerStand
}

vi.mock('../api/monatsdaten', () => ({
  monatsdatenApi: { listAggregiert: vi.fn(() => Promise.resolve(aggregiert)) },
}))

/** Die Jahresroute für ein Jahr: Kopf = Σ der Monate mit Daten (2025 → 900 kWh · 2024 → 200 kWh). */
function jahrAntwort(jahr: number) {
  const n = MONATE_JE_JAHR[jahr].length
  return cockpitJahr(jahr, {
    monate: MONATE_JE_JAHR[jahr].map((m) => monatsAntwort(jahr, m)),
    kopf: {
      anlage_name: 'Demo', pv_erzeugung_kwh: PV_JE_MONAT[jahr] * n, einspeisung_kwh: 120 * n, netzbezug_kwh: 90 * n,
      eigenverbrauch_kwh: 180 * n, direktverbrauch_kwh: 140 * n, gesamtverbrauch_kwh: 270 * n,
      autarkie_prozent: (180 / 270) * 100, eigenverbrauch_quote_prozent: 60, netto_ertrag_euro: 35 * n,
    },
  })
}

vi.mock('../api/aktuellerMonat', () => ({
  aktuellerMonatApi: { getData: vi.fn(() => Promise.reject(new Error('Cockpit → Jahr lädt keine Einzelmonate mehr'))) },
}))

vi.mock('../api/cockpit', () => ({
  cockpitApi: {
    getNachhaltigkeit: vi.fn(() => Promise.resolve(nachhaltigkeit)),
    getJahr: vi.fn((_id: number, j: number) => {
      if (!H.angehalten.has(j)) return Promise.resolve(jahrAntwort(j))
      return new Promise((res) => { H.wartend.set(`${j}`, () => res(jahrAntwort(j))) })
    }),
  },
}))

vi.mock('../api/zaehlerstaende', () => ({
  zaehlerstaendeApi: {
    get: vi.fn((_id: number, opts: { jahr?: number }) =>
      Promise.resolve([zaehlerStand(opts.jahr!)])),
  },
}))

import CockpitJahrV4 from './CockpitJahrV4'

async function ruhe() {
  await act(async () => { await new Promise((r) => setTimeout(r, 0)) })
}

describe('Cockpit → Jahr: alle Blöcke gehören demselben Jahr', () => {
  beforeEach(() => {
    localStorage.clear()
    stubMatchMedia()
    _clearSwrCacheForTests()
    H.wartend.clear()
    H.angehalten.clear()
    vi.clearAllMocks()
  })

  /** Sicht öffnen (Default = 2025), aufklappen, auf 2024 blättern — dessen
   *  Jahres-Abruf hängt, alles Client-Abgeleitete wäre sofort umgesprungen. */
  async function blaettereAufNeu() {
    H.angehalten.add(NEU)
    renderMitProvidern(<CockpitJahrV4 anlageId={1} />)
    await screen.findByText('Kennzahlen')
    await ruhe()   // der Erst-Load rendert mehrfach nach — erst danach greifen
    fireEvent.click(screen.getByText('alle aufklappen'))
    await ruhe()
    fireEvent.click(screen.getAllByRole('button', { name: 'voriges Jahr' })[0])
    await ruhe()
  }

  function loeseNeuAus() {
    H.wartend.get(`${NEU}`)?.()
  }

  it('① Paarung: die CO₂-Reihe des gewählten Jahres steht nicht unter den alten Kacheln', async () => {
    await blaettereAufNeu()
    // Die Kacheln stehen noch auf 2025 (900 kWh = 3 × 300; die Zahl steht in der
    // Kachel UND im Rail-Balken — deshalb `getAllByText`).
    expect(screen.getAllByText('900').length).toBeGreaterThan(0)
    // … also gehört auch die CO₂-Kachel weiter zu 2025 (Untertitel + Wert).
    expect(screen.getByText('2025 · PV + Wärmepumpe + E-Mobilität')).toBeInTheDocument()
    expect(screen.queryByText('2024 · PV + Wärmepumpe + E-Mobilität')).not.toBeInTheDocument()
    // Zählerstand: der des gewählten Jahres ist längst da, sichtbar wird er
    // erst mit seinen Mengen.
    expect(screen.queryByText('5.678,0')).not.toBeInTheDocument()
  })

  it('② Vorhalt: die Zahlen des angezeigten Jahres bleiben stehen, während das neue lädt', async () => {
    await blaettereAufNeu()
    expect(screen.getAllByText('900').length).toBeGreaterThan(0)
    expect(screen.getByText('2025 · PV + Wärmepumpe + E-Mobilität')).toBeInTheDocument()
  })

  it('③ Kopf: Überschrift nennt das Jahr der Zahlen, das gewählte steht als Lade-Marker daneben', async () => {
    await blaettereAufNeu()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('2025')
    expect(screen.getByText('lädt 2024 …')).toBeInTheDocument()
  })

  it('④ Nachlauf: sobald die Mengen da sind, wechselt die ganze Sicht auf das neue Jahr', async () => {
    await blaettereAufNeu()
    await act(async () => { loeseNeuAus() })
    await ruhe()
    expect((await screen.findAllByText('200')).length).toBeGreaterThan(0)
    expect(screen.getByText('2024 · PV + Wärmepumpe + E-Mobilität')).toBeInTheDocument()
    expect(screen.queryByText('2025 · PV + Wärmepumpe + E-Mobilität')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('2024')
    expect(screen.queryByText(/^lädt /)).not.toBeInTheDocument()
  })

  it('⑤ Zählerstände: der Stand folgt dem angezeigten Jahr, nicht der Auswahl', async () => {
    await blaettereAufNeu()
    expect(screen.queryByText('5.678,0')).not.toBeInTheDocument()
    await act(async () => { loeseNeuAus() })
    await ruhe()
    expect(screen.getByText('5.678,0')).toBeInTheDocument()
    expect(screen.queryByText('1.234,0')).not.toBeInTheDocument()
  })
})
