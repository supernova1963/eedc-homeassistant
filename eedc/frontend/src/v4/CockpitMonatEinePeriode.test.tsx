/**
 * Cockpit → Monat zeigt EINE Periode — dieselbe Regel wie in Cockpit → Tag.
 *
 * Die Sicht hängt an **vier** periodengebundenen Quellen mit denselben
 * Abhängigkeiten: Kacheln/Mengen (`tageQ`), Auswertungen (`auswQ`, u. a. die
 * PR-Ø-Kachel), Wärme/Klima-Verlauf (`verlaufQ`) und die Zählerstände. Sie
 * antworten nacheinander — ohne gemeinsame Marke steht die Analyse des einen
 * Monats über den Mengen eines anderen.
 *
 * Fünf Proben, je eine Klausel:
 *  1. **Paarung** — kein Wert des gewählten Monats, solange die Kacheln alt sind
 *     (geprüft an der PR-Kachel aus `auswQ` UND an der Aufteilungs-Zeile aus `verlaufQ`).
 *  2. **Vorhalt** — die Zahlen des angezeigten Monats bleiben vollständig stehen.
 *  3. **Kopf** — Überschrift nennt den Monat der ZAHLEN, der gewählte steht als Marker.
 *  4. **Nachlauf** — sobald die Mengen da sind, wechselt die ganze Sicht.
 *  5. **Zählerstände** — der Stand des einen Fensters erscheint nie unter der
 *     anderen Periode, in beide Richtungen.
 *
 * Aufbau: `aktuellerMonatApi.getData` des Ziel-Monats wird angehalten (damit hängt
 * `tageQ` als Ganzes), die drei Nebenquellen antworten sofort — genau die
 * Reihenfolge, die die Mischung erzeugt.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, act } from '@testing-library/react'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'
import type { WaermeVerlaufTag } from '../api/energie_profil'
import type { ZaehlerStand } from '../api/zaehlerstaende'

const A = { jahr: 2025, monat: 1 }   // der angezeigte Monat
const B = { jahr: 2025, monat: 2 }   // der gewählte Monat, dessen Mengen hängen
const key = (j: number, m: number) => `${j}-${m}`

/** Einzelwerte, an denen im DOM zu erkennen ist, welcher Monat gerade spricht. */
const PV_KWH: Record<string, number> = { [key(2025, 1)]: 111, [key(2025, 2)]: 222 }
const PR: Record<string, number> = { [key(2025, 1)]: 0.71, [key(2025, 2)]: 0.82 }
/** Verlauf: „Aufgeteilte Menge X von Y kWh" (Betriebsart-Stapel je Monat). */
const SPLIT: Record<string, { bezug: number; strom: number }> = {
  [key(2025, 1)]: { bezug: 5, strom: 10 },
  [key(2025, 2)]: { bezug: 7, strom: 14 },
}
/** Zählerstände: der Endstand des Fensters. */
const ZAEHLER_ENDE: Record<string, number> = { [key(2025, 1)]: 1234, [key(2025, 2)]: 5678 }

const H = vi.hoisted(() => ({
  /** Mengen-Abruf (`aktuellerMonatApi.getData`) — hält die Kachel-Abfrage als Ganzes. */
  wartend: new Map<string, () => void>(),
  angehalten: new Set<string>(),
  /** Die drei Nebenquellen (Auswertung · Verlauf · Zählerstände) desselben Monats. */
  wartendNeben: new Map<string, () => void>(),
  angehaltenNeben: new Set<string>(),
}))

import { aktuellerMonat, monatsZeile, tagWerte } from '../test/factories'
import { renderMitProvidern, stubMatchMedia } from '../test/render'
import { _clearSwrCacheForTests } from '../hooks/useApiData'

const aggregiert: AggregierteMonatsdaten[] = [
  monatsZeile(2025, 1, { pv_erzeugung_kwh: PV_KWH[key(2025, 1)], autarkie_prozent: 60 }),
  monatsZeile(2025, 2, { pv_erzeugung_kwh: PV_KWH[key(2025, 2)], autarkie_prozent: 60 }),
]

function monatsAntwort(jahr: number, monat: number) {
  return aktuellerMonat(jahr, monat, {
    anlage_name: 'Demo', monat_name: String(monat),
    pv_erzeugung_kwh: PV_KWH[key(jahr, monat)] ?? 0,
    einspeisung_kwh: 40, netzbezug_kwh: 30, eigenverbrauch_kwh: 60,
    direktverbrauch_kwh: 40, gesamtverbrauch_kwh: 90, autarkie_prozent: 60,
    eigenverbrauch_quote_prozent: 55,
    wp_strom_kwh: 60, wp_waerme_kwh: 180, hat_waermepumpe: true,
    netto_ertrag_euro: 20,
  })
}

/** Ein Monatstag des Wärme/Klima-Verlaufs mit Betriebsart-Stapel. */
function verlaufTag(jahr: number, monat: number, tag: number): WaermeVerlaufTag {
  const s = SPLIT[key(jahr, monat)]
  return {
    datum: `${jahr}-${String(monat).padStart(2, '0')}-${String(tag).padStart(2, '0')}`,
    wp_strom_kwh: s.strom, wp_waerme_kwh: null, temperatur_c: 5,
    wp_modus_strom_heizen_kwh: s.bezug, wp_modus_strom_warmwasser_kwh: null,
    wp_modus_strom_kuehlen_kwh: null, wp_modus_strom_lueften_kwh: null,
    wp_modus_strom_entfeuchten_kwh: null, wp_modus_nicht_aufgeteilt_kwh: null,
    wp_modus_strom_bezug_kwh: s.bezug, wp_modus_abdeckung_h: 24, wp_modus_gemessen: true,
  }
}

function zaehlerStand(jahr: number, monat: number): ZaehlerStand {
  const ende = ZAEHLER_ENDE[key(jahr, monat)] ?? 0
  return {
    investition_id: 1, name: 'Gaszähler', art: 'gas', einheit: 'm³',
    stand_anfang: 1000, stand_ende: ende, differenz: ende - 1000,
    anfang_vollstaendig: true, rueckwaerts: false, verlauf: [],
  } as unknown as ZaehlerStand
}

vi.mock('../api/monatsdaten', () => ({
  monatsdatenApi: { listAggregiert: vi.fn(() => Promise.resolve(aggregiert)) },
}))

vi.mock('../api/aktuellerMonat', () => ({
  aktuellerMonatApi: {
    getData: vi.fn((_id: number, j: number, m: number) => {
      const k = `${j}-${m}`
      if (!H.angehalten.has(k)) return Promise.resolve(monatsAntwort(j, m))
      return new Promise((res) => { H.wartend.set(k, () => res(monatsAntwort(j, m))) })
    }),
  },
}))

vi.mock('../api/energie_profil', () => ({
  energieProfilApi: {
    getTageWerte: vi.fn((_id: number, von: string) => Promise.resolve([
      tagWerte(`${von.slice(0, 8)}05`, { erzeugung: 10 }),
    ])),
    getVerfuegbareMonate: vi.fn(() => Promise.resolve([
      { jahr: 2025, monat: 1 }, { jahr: 2025, monat: 2 },
    ])),
    // Die Auswertungs-Antwort trägt die PR-Ø-Kachel — ein Einzelwert je Monat.
    // Die Listenfelder sind leer: geprüft wird die Zuordnung, nicht die Analyse.
    getMonat: vi.fn((_id: number, j: number, m: number) => {
      const antwort = {
      jahr: j, monat: m, tage_im_monat: 31, tage_mit_daten: 20,
      pv_kwh: 0, verbrauch_kwh: 0, einspeisung_kwh: 0, netzbezug_kwh: 0,
      ueberschuss_kwh: 0, defizit_kwh: 0, autarkie_prozent: null, eigenverbrauch_prozent: null,
      performance_ratio_avg: PR[`${j}-${m}`], performance_ratio_tage: 20,
      batterie_vollzyklen_summe: null, grundbedarf_kw: null,
      batterie_ladung_kwh: null, batterie_entladung_kwh: null, batterie_wirkungsgrad: null,
      direkt_eigenverbrauch_kwh: null,
      pv_tag_best_kwh: null, pv_tag_schnitt_kwh: null, pv_tag_schlecht_kwh: null,
      typisches_tagesprofil: [], kategorien: [], komponenten: [],
      peak_netzbezug: [], peak_einspeisung: [],
      }
      const k = `${j}-${m}`
      if (!H.angehaltenNeben.has(k)) return Promise.resolve(antwort)
      return new Promise((res) => { H.wartendNeben.set(`ausw:${k}`, () => res(antwort)) })
    }),
    getWaermeVerlauf: vi.fn((_id: number, von: string) => {
      const j = Number(von.slice(0, 4)); const m = Number(von.slice(5, 7))
      const k = `${j}-${m}`
      if (!H.angehaltenNeben.has(k)) return Promise.resolve([verlaufTag(j, m, 5)])
      return new Promise((res) => { H.wartendNeben.set(`verlauf:${k}`, () => res([verlaufTag(j, m, 5)])) })
    }),
  },
}))

vi.mock('../api/zaehlerstaende', () => ({
  zaehlerstaendeApi: {
    get: vi.fn((_id: number, opts: { jahr?: number; monat?: number }) => {
      const k = `${opts.jahr}-${opts.monat}`
      if (!H.angehaltenNeben.has(k)) return Promise.resolve([zaehlerStand(opts.jahr!, opts.monat!)])
      return new Promise((res) => {
        H.wartendNeben.set(`zaehler:${k}`, () => res([zaehlerStand(opts.jahr!, opts.monat!)]))
      })
    }),
  },
}))

vi.mock('../api/cockpit', () => ({
  cockpitApi: { getUebersicht: vi.fn(() => Promise.resolve(null)) },
}))

import CockpitMonatV4 from './CockpitMonatV4'

async function ruhe() {
  await act(async () => { await new Promise((r) => setTimeout(r, 0)) })
}

describe('Cockpit → Monat: alle Blöcke gehören demselben Monat', () => {
  beforeEach(() => {
    localStorage.clear()
    stubMatchMedia()
    _clearSwrCacheForTests()
    H.wartend.clear()
    H.angehalten.clear()
    H.wartendNeben.clear()
    H.angehaltenNeben.clear()
    vi.clearAllMocks()
  })

  /** Sicht auf Monat A öffnen, aufklappen, auf B blättern. Dessen Mengen hängen
   *  immer; `nebenquellenHaengen` hält zusätzlich Auswertung, Verlauf und
   *  Zählerstände von B an — nur dann steht der alte Monat VOLLSTÄNDIG (sonst
   *  antworten die Nebenquellen zuerst, und die Paarung blendet sie aus). */
  async function blaettereAufB(nebenquellenHaengen = false) {
    H.angehalten.add(key(B.jahr, B.monat))
    if (nebenquellenHaengen) H.angehaltenNeben.add(key(B.jahr, B.monat))
    renderMitProvidern(<CockpitMonatV4 anlageId={1} />, {
      route: `/v4/cockpit/monat?jahr=${A.jahr}&monat=${A.monat}`,
    })
    expect(await screen.findByText(/111 kWh PV/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('alle aufklappen'))
    await ruhe()
    fireEvent.click(screen.getAllByRole('button', { name: 'nächster Monat' })[0])
    await ruhe()
  }

  it('① Paarung: weder die Auswertung noch der Verlauf des gewählten Monats stehen unter den alten Kacheln', async () => {
    await blaettereAufB()
    expect(screen.getByText(/111 kWh PV/)).toBeInTheDocument()
    // PR-Ø-Kachel (aus der Auswertungs-Antwort) und Aufteilungs-Zeile (aus dem
    // Verlauf) müssen beim angezeigten Monat bleiben.
    expect(screen.queryByText('0,82')).not.toBeInTheDocument()
    expect(screen.queryByText('7 von 14 kWh')).not.toBeInTheDocument()
  })

  it('② Vorhalt: die Zahlen des angezeigten Monats bleiben vollständig stehen', async () => {
    await blaettereAufB(true)
    expect(screen.getByText(/111 kWh PV/)).toBeInTheDocument()   // Mengen
    expect(screen.getByText('0,71')).toBeInTheDocument()         // Auswertung
    expect(screen.getByText('5 von 10 kWh')).toBeInTheDocument() // Verlauf
    expect(screen.getByText('1.234,0')).toBeInTheDocument()      // Zählerstand
  })

  it('③ Kopf: Überschrift nennt den Monat der Zahlen, der gewählte steht als Lade-Marker daneben', async () => {
    await blaettereAufB()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Jan 2025')
    expect(screen.getByText('lädt Feb 2025 …')).toBeInTheDocument()
  })

  it('④ Nachlauf: sobald die Mengen da sind, wechselt die ganze Sicht auf den neuen Monat', async () => {
    await blaettereAufB()
    await act(async () => { H.wartend.get(key(B.jahr, B.monat))!() })
    await ruhe()
    expect(await screen.findByText(/222 kWh PV/)).toBeInTheDocument()
    expect(screen.getByText('0,82')).toBeInTheDocument()
    expect(screen.getByText('7 von 14 kWh')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Feb 2025')
    expect(screen.queryByText(/^lädt /)).not.toBeInTheDocument()
  })

  it('⑤ Zählerstände: der Stand des gewählten Fensters steht nicht unter der alten Periode', async () => {
    await blaettereAufB()
    // Der Stand des GEWÄHLTEN Monats ist längst da (eigener, schneller Abruf) —
    // sichtbar wird er erst mit seinen Mengen. Bis dahin zeigt der Block lieber
    // nichts als den falschen Stand (der Hook hält nur EIN Fenster).
    expect(screen.getByText(/111 kWh PV/)).toBeInTheDocument()
    expect(screen.queryByText('5.678,0')).not.toBeInTheDocument()
    await act(async () => { H.wartend.get(key(B.jahr, B.monat))!() })
    await ruhe()
    expect(screen.getByText('5.678,0')).toBeInTheDocument()
    expect(screen.queryByText('1.234,0')).not.toBeInTheDocument()
  })

  it('⑥ Zählerstände, Gegenrichtung: der alte Stand bleibt nicht unter der neuen Periode stehen', async () => {
    await blaettereAufB(true)
    // Solange der alte Monat angezeigt wird, steht sein Stand da …
    expect(screen.getByText('1.234,0')).toBeInTheDocument()
    // … sobald die Mengen des neuen Monats da sind, verschwindet er — obwohl
    // sein eigener Abruf noch läuft. Ein Zählerstand aus dem Januar unter den
    // Februar-Mengen wäre genau die Mischung, um die es geht.
    await act(async () => { H.wartend.get(key(B.jahr, B.monat))!() })
    await ruhe()
    expect(screen.getByText(/222 kWh PV/)).toBeInTheDocument()
    expect(screen.queryByText('1.234,0')).not.toBeInTheDocument()
    expect(screen.queryByText('5.678,0')).not.toBeInTheDocument()
    // Antwortet er, steht der richtige Stand da.
    await act(async () => { H.wartendNeben.get(`zaehler:${key(B.jahr, B.monat)}`)!() })
    await ruhe()
    expect(screen.getByText('5.678,0')).toBeInTheDocument()
  })
})

