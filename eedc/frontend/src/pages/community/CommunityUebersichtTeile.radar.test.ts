/**
 * N-742 (12.10.2026) — Radar «Performance-Profil»: Autarkie und Eigenverbrauch
 * stehen gegen den Community-Durchschnitt DESSELBEN Monats, nicht gegen Konstanten.
 *
 * Bis 12.10.2026 hieß die zweite Serie «Community», trug aber auf diesen beiden
 * Achsen die festen Zahlen 65 und 45; «du» war der neueste Monat — auch der
 * laufende. Konzeptentscheid Gernot 12.10.: Vergleichsbasis ist
 * `/benchmark/monat/{jahr}/{monat}` (`.autarkie.durchschnitt`,
 * `.eigenverbrauch.durchschnitt`) für den letzten abgeschlossenen Monat der Anlage.
 *
 * Die Proben unten sind so gebaut, dass jede eine der vier Eigenschaften allein
 * prüft: (1) keine Konstanten — zwei verschiedene Server-Antworten ergeben zwei
 * verschiedene Community-Werte; (2) gleiche Zeitbasis — eine Antwort für einen
 * anderen Monat zählt nicht; (3) laufender Monat ausgeschlossen; (4) `null` lässt
 * die Achse wegfallen, 0 % bleibt ein Wert.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import type { CommunityBenchmarkResponse, MonatsVergleich, MonatswertOutput } from '../../api/community'
import { communityApi } from '../../api/community'
import { baueRadarDaten, radarVergleichsMonat, useUebersichtDaten, RADAR_MIN_ANLAGEN_MONAT, type RadarAchse } from './CommunityUebersichtTeile'

const HEUTE = new Date(2026, 9, 12) // 12.10.2026 — Oktober läuft

function zeile(jahr: number, monat: number, autarkie: number | null, ev: number | null): MonatswertOutput {
  return { jahr, monat, ertrag_kwh: 500, autarkie_prozent: autarkie, eigenverbrauch_prozent: ev }
}

// Absteigend wie vom Server (F-25); der laufende Oktober ist mitgeschickt.
const MONATSWERTE: MonatswertOutput[] = [
  zeile(2026, 10, 99, 99),
  zeile(2026, 9, 70, 55),
  zeile(2026, 8, 85, 50),
]

function benchmark(monatswerte: MonatswertOutput[] = MONATSWERTE): CommunityBenchmarkResponse {
  return {
    anlage: {
      anlage_hash: 'x', region: 'BY', kwp: 10, ausrichtung: 'Süd', neigung_grad: 30,
      installation_jahr: 2022, hat_waermepumpe: false, hat_eauto: false, hat_wallbox: false,
      hat_balkonkraftwerk: false, hat_sonstiges: false, monatswerte,
    },
    benchmark: {
      spez_ertrag_anlage: 1000, spez_ertrag_durchschnitt: 950, spez_ertrag_region: 960,
      rang_gesamt: 10, anzahl_anlagen_gesamt: 100, rang_region: 2, anzahl_anlagen_region: 10,
    },
    benchmark_erweitert: {},
    zeitraum: 'letzte_12_monate',
    zeitraum_label: 'letzte 12 Monate',
  }
}

const kpi = (durchschnitt: number | null, anzahl = 71) => ({ durchschnitt, median: null, min: null, max: null, anzahl_anlagen: anzahl })

function monatsVergleich(jahr: number, monat: number, autarkie: number | null, ev: number | null): MonatsVergleich {
  return {
    jahr, monat, anzahl_anlagen: 71,
    spez_ertrag: kpi(80),
    autarkie: autarkie === null ? null : kpi(autarkie),
    eigenverbrauch: ev === null ? null : kpi(ev),
    einspeisung: null, netzbezug: null,
  }
}

const achse = (daten: RadarAchse[], k: string) => daten.find((a) => a.kategorie === k)

describe('radarVergleichsMonat — der letzte abgeschlossene Monat', () => {
  it('überspringt den laufenden Monat, egal in welcher Reihenfolge die Liste kommt', () => {
    expect(radarVergleichsMonat(MONATSWERTE, HEUTE)).toMatchObject({ jahr: 2026, monat: 9 })
    expect(radarVergleichsMonat([...MONATSWERTE].reverse(), HEUTE)).toMatchObject({ jahr: 2026, monat: 9 })
  })

  it('nimmt einen älteren Monat, wenn die Anlage zuletzt vor Monaten geteilt hat', () => {
    expect(radarVergleichsMonat([zeile(2026, 6, 80, 40), zeile(2026, 5, 70, 45)], HEUTE)).toMatchObject({ jahr: 2026, monat: 6 })
  })

  it('kennt die Jahresgrenze (Januar läuft ⇒ Dezember des Vorjahres)', () => {
    const werte = [zeile(2027, 1, 10, 90), zeile(2026, 12, 12, 88)]
    expect(radarVergleichsMonat(werte, new Date(2027, 0, 5))).toMatchObject({ jahr: 2026, monat: 12 })
  })

  it('liefert nichts, wenn nur der laufende Monat da ist', () => {
    expect(radarVergleichsMonat([zeile(2026, 10, 99, 99)], HEUTE)).toBeUndefined()
    expect(radarVergleichsMonat(undefined, HEUTE)).toBeUndefined()
  })
})

describe('baueRadarDaten — Community-Werte aus dem Monats-Benchmark', () => {
  const sept = radarVergleichsMonat(MONATSWERTE, HEUTE)

  it('nimmt Autarkie und Eigenverbrauch der Community aus `.durchschnitt` — keine Konstanten', () => {
    const a = baueRadarDaten(benchmark(), sept, monatsVergleich(2026, 9, 80.5, 58.8))
    const b = baueRadarDaten(benchmark(), sept, monatsVergleich(2026, 9, 20, 90))
    expect(achse(a, 'Autarkie')).toMatchObject({ du: 70, community: 80.5 })
    expect(achse(a, 'Eigenverbrauch')).toMatchObject({ du: 55, community: 58.8 })
    // Eine andere Server-Antwort ⇒ ein anderes Polygon. Mit 65/45 wäre beides gleich.
    expect(achse(b, 'Autarkie')).toMatchObject({ du: 70, community: 20 })
    expect(achse(b, 'Eigenverbrauch')).toMatchObject({ du: 55, community: 90 })
    for (const d of [...a, ...b]) {
      expect(d.community).not.toBe(65)
      expect(d.community).not.toBe(45)
    }
  })

  it('«du» ist derselbe Monat wie die Community-Basis, nicht der laufende', () => {
    const d = baueRadarDaten(benchmark(), sept, monatsVergleich(2026, 9, 80, 60))
    // 99 % stammen aus dem laufenden Oktober und dürfen nicht erscheinen.
    expect(achse(d, 'Autarkie')!.du).toBe(70)
    expect(achse(d, 'Eigenverbrauch')!.du).toBe(55)
  })

  it('eine Monats-Antwort für einen ANDEREN Monat zählt nicht (gleiche Zeitbasis)', () => {
    const d = baueRadarDaten(benchmark(), sept, monatsVergleich(2026, 8, 80, 60))
    expect(achse(d, 'Autarkie')).toBeUndefined()
    expect(achse(d, 'Eigenverbrauch')).toBeUndefined()
  })

  it('ohne Server-Basis (null) fällt die Achse weg — nichts wird eingesetzt', () => {
    const ohneAutarkie = baueRadarDaten(benchmark(), sept, monatsVergleich(2026, 9, null, 60))
    expect(achse(ohneAutarkie, 'Autarkie')).toBeUndefined()
    expect(achse(ohneAutarkie, 'Eigenverbrauch')).toMatchObject({ community: 60 })
    const ohneAntwort = baueRadarDaten(benchmark(), sept, null)
    expect(ohneAntwort.map((x) => x.kategorie)).toEqual(['PV-Ertrag'])
    // < 3 Achsen ⇒ der Block entfällt in `CommunityUebersichtV4` (≥ 3 Achsen).
    expect(ohneAntwort.length).toBeLessThan(3)
  })

  it('Mindestzahl: unter drei Anlagen hinter dem Monatswert fällt die Achse weg (Entscheid Master 12.10.)', () => {
    expect(RADAR_MIN_ANLAGEN_MONAT).toBe(3)
    const mit = (n: number): MonatsVergleich => ({
      ...monatsVergleich(2026, 9, null, null),
      autarkie: kpi(70, n),
      eigenverbrauch: kpi(55, n),
    })
    // Zwei Anlagen, eine davon die eigene: der «Community»-Wert spiegelt sich selbst.
    const zwei = baueRadarDaten(benchmark(), sept, mit(2))
    expect(achse(zwei, 'Autarkie')).toBeUndefined()
    expect(achse(zwei, 'Eigenverbrauch')).toBeUndefined()
    const drei = baueRadarDaten(benchmark(), sept, mit(3))
    expect(achse(drei, 'Autarkie')).toMatchObject({ community: 70, basisAnlagen: 3 })
    expect(achse(drei, 'Eigenverbrauch')).toMatchObject({ community: 55, basisAnlagen: 3 })
  })

  it('0 % ist ein Wert, `null` beim eigenen Monat lässt die Achse wegfallen', () => {
    const werte = [zeile(2026, 9, 0, null)]
    const d = baueRadarDaten(benchmark(werte), radarVergleichsMonat(werte, HEUTE), monatsVergleich(2026, 9, 0, 40))
    expect(achse(d, 'Autarkie')).toMatchObject({ du: 0, community: 0 })
    expect(achse(d, 'Eigenverbrauch')).toBeUndefined()
  })
})

describe('useUebersichtDaten — lädt den Monats-Benchmark des Vergleichsmonats', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('fragt September an (nicht den laufenden Oktober) und nennt den Monat', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(HEUTE)
    const spy = vi.spyOn(communityApi, 'getMonatsBenchmark').mockResolvedValue(monatsVergleich(2026, 9, 72, 56.7))
    const { result } = renderHook(() => useUebersichtDaten(benchmark()))
    await waitFor(() => expect(achse(result.current.radarData, 'Autarkie')).toBeDefined())
    expect(spy).toHaveBeenCalledWith(2026, 9)
    expect(spy).not.toHaveBeenCalledWith(2026, 10)
    expect(achse(result.current.radarData, 'Autarkie')).toMatchObject({ du: 70, community: 72 })
    expect(result.current.radarMonat).toEqual({ jahr: 2026, monat: 9, anlagenVon: 71, anlagenBis: 71 })
  })

  it('404 «Keine Daten für den Monat» ⇒ keine Monatsachsen, kein Monat im Untertitel', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(HEUTE)
    const spy = vi.spyOn(communityApi, 'getMonatsBenchmark').mockRejectedValue(new Error('404'))
    const { result } = renderHook(() => useUebersichtDaten(benchmark()))
    await waitFor(() => expect(spy).toHaveBeenCalled())
    await new Promise((r) => setTimeout(r, 0))
    expect(result.current.radarData.map((a) => a.kategorie)).toEqual(['PV-Ertrag'])
    expect(result.current.radarMonat).toBeNull()
  })
})
