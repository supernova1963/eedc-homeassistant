/**
 * Der Block muss die gedeckelte Zahl **einordnen**, nicht nur anzeigen.
 *
 * „0 kWh" ohne Satz daneben liest sich wie ein fehlender Wert. Genau deshalb gibt
 * es den Befund-Text — und deshalb prüfen diese Tests ihn, nicht die Kacheln.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { SpeicherPotentialIST } from './SpeicherPotentialIST'
import {
  investitionenApi,
  type MonatsPotential,
  type SpeicherPotentialResponse,
} from '../api/investitionen'

vi.mock('../components/park', () => ({
  Parkbar: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  usePark: () => ({ istGeparkt: () => false }),
}))

const ANTWORT = (teil: Partial<SpeicherPotentialResponse> = {}): SpeicherPotentialResponse => ({
  nutzbares_zusatzpotential_kwh: 0,
  ueberschuss_kwh: 471.6,
  stunden_voll: 114,
  zyklen_gesamt: 14,
  zyklen_leergelaufen: 0,
  deckelung_greift: true,
  tage_mit_daten: 12,
  von: '2026-06-10',
  bis: '2026-06-21',
  monate: [MONAT()],
  anzahl_speicher: 1,
  kapazitaet_kwh: 9.2,
  kapazitaet_brutto_kwh: 10,
  soc_voll_prozent: 95,
  soc_leer_prozent: 5,
  ...teil,
})

const MONAT = (teil: Partial<MonatsPotential> = {}): MonatsPotential => ({
  jahr: 2026, monat: 6,
  nutzbares_zusatzpotential_kwh: 0, ueberschuss_kwh: 471.6,
  stunden_voll: 114, zyklen_gesamt: 14, zyklen_leergelaufen: 0,
  stunden_mit_soc: 288,
  soc_p10: 42, soc_p50: 78, soc_p90: 100,
  anteil_voll_prozent: 39.6, anteil_leer_prozent: 0,
  vollzyklen: 18.4,
  ladung_kwh: 190, netz_ladung_kwh: 0, netz_ladung_anteil_prozent: 0,
  ...teil,
})

describe('SpeicherPotentialIST', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('sagt bei 0 kWh ausdrücklich, dass mehr Kapazität nichts gebracht hätte', async () => {
    // Der real gemessene Juni-Fall: 471,6 kWh Überschuss, aber keine leere Nacht.
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT())

    render(<SpeicherPotentialIST anlageId={1} />)

    await waitFor(() => {
      expect(screen.getByText(/nichts gebracht/i)).toBeInTheDocument()
    })
    // Die Obergrenze wird genannt — aber als Kontext, nicht als Versprechen.
    expect(screen.getByText(/472 kWh/)).toBeInTheDocument()
  })

  it('nennt bei echtem Potential die Nächte als Begrenzung', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT({
      nutzbares_zusatzpotential_kwh: 29.3,
      ueberschuss_kwh: 227.0,
      zyklen_gesamt: 8,
      zyklen_leergelaufen: 4,
    }))

    render(<SpeicherPotentialIST anlageId={1} />)

    await waitFor(() => {
      expect(screen.getByText(/4 von 8 Mal/)).toBeInTheDocument()
    })
    expect(screen.getByText(/29 kWh/)).toBeInTheDocument()
  })

  it('unterscheidet „kein Potential" von „keine Daten"', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT({
      tage_mit_daten: 0, monate: [], zyklen_gesamt: 0, ueberschuss_kwh: 0,
    }))

    render(<SpeicherPotentialIST anlageId={1} />)

    await waitFor(() => {
      expect(screen.getByText(/fehlen Stundenwerte/i)).toBeInTheDocument()
    })
    expect(screen.queryByText(/nichts gebracht/i)).not.toBeInTheDocument()
  })

  it('sagt bei mehreren Speichern, dass nur EIN Gerät ausgewertet wird', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(
      ANTWORT({ anzahl_speicher: 2 }),
    )

    render(<SpeicherPotentialIST anlageId={1} />)

    await waitFor(() => {
      // N-239: der Ladestand kommt vom ERSTEN gemappten Sensor, nicht aus einer
      // Mischung — die Sicht darf keine anlagenweite Aussage behaupten.
      expect(screen.getByText(/kapazitätsgewichtete/i)).toBeInTheDocument()
    })
  })

  it('meldet die Park-ID erst, wenn wirklich etwas zu zeigen ist', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(
      ANTWORT({ tage_mit_daten: 0, monate: [] }),
    )
    const melde = vi.fn()

    render(<SpeicherPotentialIST anlageId={1} melde={melde} />)

    await waitFor(() => expect(melde).toHaveBeenCalled())
    expect(melde).toHaveBeenLastCalledWith([])
  })

  // Bis 2026-08-15 lag EINE Parkbar um den ganzen Block: Befund, drei Kacheln,
  // Spuren-Grafik und Hinweis ließen sich nur gemeinsam parken, und beim
  // Rechtsklick verdunkelte sich alles statt der angefassten Kachel. Die
  // gemeldeten IDs sind der beobachtbare Vertrag mit dem Block (`alleGeparkt`)
  // — eine einzige ID hieße wieder ein Bündel.
  it('meldet jede Teil-Anzeige einzeln, nicht das Bündel', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(
      ANTWORT({ anzahl_speicher: 2 }),
    )
    const melde = vi.fn()

    render(<SpeicherPotentialIST anlageId={1} melde={melde} />)

    // Der erste Lauf meldet `[]` (noch am Laden) — gewartet wird auf die Meldung
    // MIT Daten, sonst prüft die Probe den Ladezustand.
    await waitFor(() => expect(melde.mock.calls.at(-1)![0]).not.toHaveLength(0))
    const ids = melde.mock.calls.at(-1)![0] as string[]
    expect(ids).toContain('speicher:potential-befund')
    expect(ids).toContain('speicher:potential-kpi-zusatz')
    expect(ids).toContain('speicher:potential-kpi-ueberschuss')
    expect(ids).toContain('speicher:potential-kpi-leer')
    expect(ids).toContain('speicher:potential-spuren')
    expect(ids).toContain('speicher:potential-hinweis')
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('meldet nur, was auch gerendert wird', async () => {
    // Ein Speicher, keine Monate ⇒ weder Spuren-Grafik noch Mehrgeräte-Hinweis.
    // Stünden sie trotzdem in der Liste, ließe sich der Block nie ganz parken.
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(
      ANTWORT({ anzahl_speicher: 1, monate: [] }),
    )
    const melde = vi.fn()

    render(<SpeicherPotentialIST anlageId={1} melde={melde} />)

    await waitFor(() => expect(melde.mock.calls.at(-1)![0]).not.toHaveLength(0))
    const ids = melde.mock.calls.at(-1)![0] as string[]
    expect(ids).not.toContain('speicher:potential-spuren')
    expect(ids).not.toContain('speicher:potential-hinweis')
    expect(ids).toContain('speicher:potential-befund')
  })
})

describe('SpeicherPotentialIST — Spannen-Grafik statt Heatmap', () => {
  beforeEach(() => vi.restoreAllMocks())

  /**
   * Der Befund, an dem die Heatmap gescheitert ist, als Test:
   * Ein Monat mit Extremwert darf die Darstellung der übrigen NICHT bestimmen.
   * Genau das tat die alte globale Deckkraft-Normierung — Okt/Nov und Feb/Mär
   * waren nicht mehr unterscheidbar (Rainer, 13.08.).
   */
  it('stellt zwei Monate unterschiedlich dar, obwohl ein dritter extrem ist', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT({
      monate: [
        MONAT({ monat: 10, soc_p10: 20, soc_p50: 35, soc_p90: 55 }),
        MONAT({ monat: 11, soc_p10: 5, soc_p50: 12, soc_p90: 25 }),
        // Der Extremmonat: früher setzte er die Skala für alle.
        MONAT({ monat: 12, soc_p10: 0, soc_p50: 0, soc_p90: 2, anteil_leer_prozent: 96 }),
      ],
    }))

    render(<SpeicherPotentialIST anlageId={1} />)

    const okt = await screen.findByTitle(/^Okt 2026 · Ladestand 20–55 %/)
    const nov = screen.getByTitle(/^Nov 2026 · Ladestand 5–25 %/)
    // Die Spanne steht in der Höhe des Balkens — und die beiden sind verschieden.
    const hoehe = (el: HTMLElement) =>
      (el.querySelector('div[style*="height"]') as HTMLElement).style.height
    expect(hoehe(okt)).not.toEqual(hoehe(nov))
  })

  it('nennt beide Anschläge im Titel — erst zusammen tragen sie die Aussage', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT({
      monate: [MONAT({ anteil_voll_prozent: 40, anteil_leer_prozent: 15 })],
    }))

    render(<SpeicherPotentialIST anlageId={1} />)

    expect(await screen.findByTitle(
      /40 % der Stunden ≥ 95 % · 15 % der Stunden ≤ 5 %/,
    )).toBeInTheDocument()
  })

  it('zeigt den Durchsatz als eigene Spur — Zustände sind keine Umsätze', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT({
      monate: [MONAT({ vollzyklen: 22.5 })],
    }))

    render(<SpeicherPotentialIST anlageId={1} />)

    expect(await screen.findByText(/bis 22,5 Vollzyklen/)).toBeInTheDocument()
    expect(screen.getByTitle(/Jun 2026: 22,5 Vollzyklen/)).toBeInTheDocument()
  })

  it('unterscheidet „keine Kapazität gepflegt" von „keine Entladung"', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT({
      kapazitaet_brutto_kwh: null,
      monate: [MONAT({ vollzyklen: null })],
    }))

    render(<SpeicherPotentialIST anlageId={1} />)

    expect(await screen.findByText(/sobald für den Speicher eine Kapazität gepflegt ist/))
      .toBeInTheDocument()
  })

  it('weist die Netzladung als Obergrenze aus, nicht als Messung', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT({
      monate: [MONAT({ netz_ladung_kwh: 48, netz_ladung_anteil_prozent: 25 })],
    }))

    render(<SpeicherPotentialIST anlageId={1} />)

    expect(await screen.findByTitle(/höchstens 25 % der Ladung aus dem Netz/))
      .toBeInTheDocument()
    expect(screen.getByText(/Obergrenze — kein Zähler trennt/)).toBeInTheDocument()
  })

  it('schweigt über die Netzladung, wenn es keine gab', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT())

    render(<SpeicherPotentialIST anlageId={1} />)

    await waitFor(() => expect(screen.getByText(/Ladestand über den Monat/)).toBeInTheDocument())
    expect(screen.queryByText(/Ladung aus dem Netz/)).not.toBeInTheDocument()
  })

  // -------------------------------------------------------------------------
  // #379 — die Leer-Schwelle gehört der Anlage, und die Sicht sagt das
  // -------------------------------------------------------------------------

  it('nennt die eigene Entladegrenze statt der Standardannahme', async () => {
    // Glens Speicher: 20 % Untergrenze, abgeleitet aus 24 von 30 kWh nutzbar.
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT({
      soc_leer_prozent: 23,
      soc_leer_ist_abgeleitet: true,
    }))

    render(<SpeicherPotentialIST anlageId={1} />)

    expect(await screen.findByText(/leer = Ladestand ≤ 23 % \(deine Entladegrenze\)/))
      .toBeInTheDocument()
    expect(screen.getByText(/nicht 0 %/)).toBeInTheDocument()
  })

  it('erklärt die Grenze nicht weg, wo sie die Standardannahme ist', async () => {
    // Ohne gepflegte nutzbare Kapazität bleibt es beim alten Text — sonst
    // behauptet die Sicht eine Einstellung, die der Anwender nie gemacht hat.
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT())

    render(<SpeicherPotentialIST anlageId={1} />)

    expect(await screen.findByText(/leer = Ladestand ≤ 5 %/)).toBeInTheDocument()
    expect(screen.queryByText(/deine Entladegrenze/)).not.toBeInTheDocument()
  })

  // -------------------------------------------------------------------------
  // N-254 — „nie leer" belegt ohne gepflegte Grenze gar nichts
  // -------------------------------------------------------------------------

  it('behauptet nichts, wo der Speicher dem Boden nie nahe kam', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT({
      boden_nie_erreicht: true,
      soc_min_prozent: 31,
    }))

    render(<SpeicherPotentialIST anlageId={1} />)

    expect(await screen.findByText(/lässt sich hier nicht beurteilen/)).toBeInTheDocument()
    expect(screen.getByText(/tiefster Ladestand war 31 %/)).toBeInTheDocument()
    expect(screen.getByText(/nutzbare Kapazität/)).toBeInTheDocument()
    // Der alte Satz darf hier NICHT stehen — er ist die falsche Tatsache.
    expect(screen.queryByText(/hätte hier nichts gebracht/)).not.toBeInTheDocument()
  })

  it('zeigt die Kachel als „—" statt als 0 kWh, wo nichts beurteilbar ist', async () => {
    // „0" wäre auch hier eine Aussage, die niemand gemessen hat.
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT({
      boden_nie_erreicht: true,
      soc_min_prozent: 31,
    }))

    render(<SpeicherPotentialIST anlageId={1} />)

    expect(await screen.findByText(/nicht beurteilbar — siehe Hinweis oben/)).toBeInTheDocument()
  })

  it('sagt weiter klar „hätte nichts gebracht", wo die Aussage belegt ist', async () => {
    // Der Fall, für den der Block gebaut wurde — er darf nicht verlorengehen.
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT({
      boden_nie_erreicht: false,
    }))

    render(<SpeicherPotentialIST anlageId={1} />)

    expect(await screen.findByText(/hätte hier nichts gebracht/)).toBeInTheDocument()
    expect(screen.queryByText(/nicht beurteilen/)).not.toBeInTheDocument()
  })

  it('sagt bei einem Monat ohne Ladestand, dass nichts gemessen wurde', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT({
      monate: [MONAT({ soc_p10: null, soc_p50: null, soc_p90: null, stunden_mit_soc: 0 })],
    }))

    render(<SpeicherPotentialIST anlageId={1} />)

    expect(await screen.findByTitle(/kein Ladestand gemessen/)).toBeInTheDocument()
  })
})
