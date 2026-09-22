/**
 * FD-5 auf der Live-Sicht — `liveFokusVorhanden` (CockpitLiveV4).
 *
 * Die Live-Sicht hat keine `BlockShell`; fünf der acht Beispiel-Anzeigen des
 * Deep-Links liegen hier. Geprüft wird die Regel, unter der eine Webseiten-Karte
 * das Hinweis-Overlay statt der ganzen Live-Sicht bekommt: unbekannte ID,
 * geparkte Kachel, fehlende Daten.
 *
 * ⚠ Reine Funktion statt Render-Probe — aus demselben Grund, aus dem
 * `boersenpreisVollGeparkt` eine hat: diese Sicht hängt an fünf Endpunkten und
 * pollt; eine Render-Probe prüfte vor allem ihre eigenen Attrappen. Dass das
 * Overlay wirklich aufgeht, hält `CockpitLiveDeepLink.test.tsx` an drei Fällen
 * fest, und der Lab-Durchklick (Gate d) fährt alle fünf IDs im Browser.
 */
import { describe, it, expect } from 'vitest'
import { LIVE_FOKUS_IDS, liveFokusVorhanden, type LiveFokusLage } from './CockpitLiveV4'
import type {
  BoersenpreisResponse, LiveDashboardResponse, LiveWetterResponse,
} from '../api/liveDashboard'

const data = (verfuegbar = true): LiveDashboardResponse => ({
  anlage_id: 1, anlage_name: 'Demo', zeitpunkt: '2026-09-22T12:00:00', verfuegbar,
  komponenten: [], summe_erzeugung_kw: 3, summe_verbrauch_kw: 1, summe_pv_kw: 3,
  gauges: [{ key: 'soc_batterie', label: 'Speicher', wert: 55, einheit: '%' } as LiveDashboardResponse['gauges'][number]],
  heute_pv_kwh: 12, heute_einspeisung_kwh: 4, heute_netzbezug_kwh: 2, heute_eigenverbrauch_kwh: 8,
  gestern_pv_kwh: 10, gestern_einspeisung_kwh: 3, gestern_netzbezug_kwh: 2, gestern_eigenverbrauch_kwh: 7,
  heute_kwh_pro_komponente: null, warmwasser_temperatur_c: 48,
})

const wetter = (): LiveWetterResponse => ({
  anlage_id: 1, verfuegbar: true, aktuell: null, stunden: [],
  temperatur_min_c: 8, temperatur_max_c: 19,
  sonnenstunden: 6, sonnenstunden_bisher: 3, sonnenstunden_rest: 3,
  pv_prognose_kwh: 20, pv_prognose_rest_kwh: 8, pv_prognose_heute_rollend_kwh: 20,
  pv_ist_bisher_kwh: 12, grundlast_kw: 0.3, verbrauchsprofil: [],
  sunrise: '2026-09-22T06:50:00', sunset: '2026-09-22T19:10:00',
} as LiveWetterResponse)

const boersen = (): BoersenpreisResponse => ({
  anlage_id: 1, markt: 'DE',
  tage: [{ datum: '2026-09-22', stunden: [] }] as unknown as BoersenpreisResponse['tage'],
  monats_durchschnitt_cent: 9, aktuelle_stunde: 12, heute: '2026-09-22', hinweis: null,
} as BoersenpreisResponse)

/** Vollständige Lage: alles da, nichts geparkt. */
function lage(over: Partial<LiveFokusLage> = {}): LiveFokusLage {
  return {
    data: data(), wetter: wetter(), prognose3Tage: [], zaehlerstaende: null,
    boersenpreise: boersen(), hatTagesverlauf: true, boersenpreisAllesGeparkt: false,
    istGeparkt: () => false,
    ...over,
  }
}

describe('liveFokusVorhanden — alle fünf Adressen der Live-Sicht', () => {
  it('kennt genau fünf IDs', () => {
    expect([...LIVE_FOKUS_IDS]).toEqual([
      'live:energiefluss', 'live:auf-einen-blick', 'live:wetter-heute',
      'live:tagesverlauf', 'live:boersenpreis',
    ])
  })

  it('bei voller Datenlage ist jede der fünf vorhanden', () => {
    for (const id of LIVE_FOKUS_IDS) {
      expect(liveFokusVorhanden(id, lage()), id).toBe(true)
    }
  })

  it('eine unbekannte ID ist nie vorhanden (FD-5 Fall 1)', () => {
    expect(liveFokusVorhanden('gibtesnicht', lage())).toBe(false)
    // Auch eine Block-ID aus einer ANDEREN Sicht zählt hier nicht.
    expect(liveFokusVorhanden('bilanz', lage())).toBe(false)
    expect(liveFokusVorhanden('live:', lage())).toBe(false)
  })
})

describe('liveFokusVorhanden — Degradation', () => {
  it('ohne Live-Daten gibt es keine der vier sensorabhängigen Anzeigen', () => {
    for (const l of [lage({ data: null }), lage({ data: data(false) })]) {
      expect(liveFokusVorhanden('live:energiefluss', l)).toBe(false)
      expect(liveFokusVorhanden('live:auf-einen-blick', l)).toBe(false)
      expect(liveFokusVorhanden('live:wetter-heute', l)).toBe(false)
      expect(liveFokusVorhanden('live:tagesverlauf', l)).toBe(false)
    }
  })

  it('… der Börsenpreis aber schon — er hängt an keinem Sensor', () => {
    expect(liveFokusVorhanden('live:boersenpreis', lage({ data: null }))).toBe(true)
  })

  it('`live:wetter-heute` fehlt, solange kein Wetter da ist', () => {
    expect(liveFokusVorhanden('live:wetter-heute', lage({ wetter: null }))).toBe(false)
    // Die anderen bleiben davon unberührt.
    expect(liveFokusVorhanden('live:energiefluss', lage({ wetter: null }))).toBe(true)
  })

  it('`live:tagesverlauf` fehlt ohne Verlaufspunkte', () => {
    expect(liveFokusVorhanden('live:tagesverlauf', lage({ hatTagesverlauf: false }))).toBe(false)
  })

  it('eine GEPARKTE Kachel gilt als nicht vorhanden (FD-5 Fall 3)', () => {
    const nur = (id: string) => lage({ istGeparkt: (x) => x === id })
    expect(liveFokusVorhanden('live:energiefluss', nur('live:energiefluss'))).toBe(false)
    expect(liveFokusVorhanden('live:wetter-heute', nur('live:wetter-heute'))).toBe(false)
    expect(liveFokusVorhanden('live:tagesverlauf', nur('live:tagesverlauf'))).toBe(false)
    expect(liveFokusVorhanden('live:boersenpreis', nur('live:boersenpreis'))).toBe(false)
  })

  it('`live:auf-einen-blick` fehlt erst, wenn ALLE seine Abschnitte geparkt sind (R2)', () => {
    // Verfügbar sind bei dieser Datenlage: heute · sonnenstand · ladezustand · temperaturen.
    const alle = ['live:heute', 'live:sonnenstand', 'live:ladezustand', 'live:temperaturen']
    expect(liveFokusVorhanden('live:auf-einen-blick', lage({
      istGeparkt: (id) => alle.includes(id),
    }))).toBe(false)
    // Einer weniger ⇒ der Block steht noch, der Deep-Link trifft ihn.
    expect(liveFokusVorhanden('live:auf-einen-blick', lage({
      istGeparkt: (id) => alle.slice(1).includes(id),
    }))).toBe(true)
  })

  it('der Börsenpreis-Block zählt nicht, wenn seine Elemente alle geparkt sind', () => {
    expect(liveFokusVorhanden('live:boersenpreis', lage({ boersenpreisAllesGeparkt: true }))).toBe(false)
  })

  it('ohne Preise und ohne Hinweis gibt es den Börsenpreis-Block nicht', () => {
    const leer = { ...boersen(), tage: [], hinweis: null } as BoersenpreisResponse
    expect(liveFokusVorhanden('live:boersenpreis', lage({ boersenpreise: leer }))).toBe(false)
    // Mit Hinweis erscheint er (er sagt dann, warum es keine Preise gibt).
    const mitHinweis = { ...leer, hinweis: 'Keine Preise abrufbar' } as BoersenpreisResponse
    expect(liveFokusVorhanden('live:boersenpreis', lage({ boersenpreise: mitHinweis }))).toBe(true)
  })
})
