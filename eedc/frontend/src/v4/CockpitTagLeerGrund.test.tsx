/**
 * Cockpit/Tag: die leere Tagessicht nennt ihren Grund — und den Knopf nur, wo er wirkt.
 *
 * Bis v4.0.9 stand hier ein Satz ohne Grund und ohne Weg. Der Grund kommt jetzt
 * aus dem Backend; die schärfste Probe ist die **Absage**: bei einem Tag vor der
 * Inbetriebnahme darf kein Reparatur-Knopf erscheinen (er verspräche eine
 * Wirkung, die es nicht gibt — Gegenstück zu #368).
 *
 * Zweite Probe: `bloecke.length === 0` ist NICHT der leere Tag (der Zweig pusht
 * immer den Kennzahlen-Block), sondern die vollständig geparkte Sicht — die
 * Card dort darf nicht „keine Daten" behaupten.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import type { TagStatus } from '../api/energie_profil'

const iso = (d: Date) => d.toISOString().slice(0, 10)
const gestern = (() => { const d = new Date(); d.setDate(d.getDate() - 1); return iso(d) })()

const LUECKE: TagStatus = {
  datum: gestern,
  lage: 'luecke_reparierbar',
  meldung: 'Dieser Tag wurde nie aggregiert — Home Assistant hat die Werte noch.',
  details: 'In der HA-Langzeitstatistik stehen für diesen Tag: Netzbezug 12.5 kWh.',
  aktion_kind: 'reaggregate_day',
  aktion_label: 'Tag nachrechnen',
}

const VOR_INBETRIEBNAHME: TagStatus = {
  datum: gestern,
  lage: 'vor_inbetriebnahme',
  meldung: 'Vor der Inbetriebnahme am 2025-06-01 — für diesen Tag gibt es keine Messwerte.',
  details: 'eedc wertet erst ab dem Inbetriebnahme-Datum der Anlage aus.',
  link: '/einstellungen/stammdaten',
}

/** Minimaler Tag MIT Werten — für den zweiten Zustand (alles geparkt). */
const TAG_MIT_WERTEN = tagWerte(gestern, {
  stunden_verfuegbar: 24, datenquelle: 'HA',
  erzeugung: 20, eigenverbrauch: 8, einspeisung: 12, netzbezug: 5,
  gesamtverbrauch: 13, direktverbrauch: 6, autarkie: 62,
})

const getTagStatus = vi.fn()
const reaggregateTag = vi.fn()

vi.mock('../api/energie_profil', () => ({
  energieProfilApi: {
    // Leere Tagessicht: keine Zeile für den gewählten Tag, keine Stunden.
    getStunden: vi.fn(() => Promise.resolve({ stunden: [], serien: [] })),
    getTageWerte: vi.fn(() => Promise.resolve([])),
    getVerfuegbareMonate: vi.fn(() => Promise.resolve([])),
    getTagDetail: vi.fn(() => Promise.resolve(null)),
    getTagStatus: (anlageId: number, datum: string) => getTagStatus(anlageId, datum),
    reaggregateTag: (...args: unknown[]) => reaggregateTag(...args),
  },
}))

import CockpitTagV4 from './CockpitTagV4'
import { _clearSwrCacheForTests } from '../hooks/useApiData'
import { renderMitProvidern, stubMatchMedia } from '../test/render'
import { tagWerte } from '../test/factories'

function renderView() {
  return renderMitProvidern(<CockpitTagV4 anlageId={1} />, { route: '/v4/cockpit/tag' })
}

describe('Cockpit/Tag — leere Sicht erklärt sich', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _clearSwrCacheForTests()
    localStorage.clear()
    stubMatchMedia()
  })

  it('nennt den Grund aus dem Backend statt nur „keine Daten"', async () => {
    getTagStatus.mockResolvedValue(LUECKE)
    renderView()

    expect(await screen.findByText(/nie aggregiert/i)).toBeInTheDocument()
    expect(screen.getByText(/12\.5 kWh/)).toBeInTheDocument()
    expect(screen.queryByText(/Wähle einen Tag mit Messwerten/i)).not.toBeInTheDocument()
  })

  it('bietet die Tagesreparatur an, wo sie wirkt', async () => {
    getTagStatus.mockResolvedValue(LUECKE)
    reaggregateTag.mockResolvedValue({
      status: 'ok', datum: gestern, stunden_verfuegbar: 24, stunden_mit_messdaten: 24,
      pv_kwh_alt: 0, pv_kwh_neu: 18.4, komponenten: [],
      komponenten_erwartet: 1, komponenten_geschrieben: 1, komponenten_ohne_wert: [],
    })
    renderView()

    const knopf = await screen.findByRole('button', { name: /Tag nachrechnen/i })
    fireEvent.click(knopf)

    await waitFor(() => expect(reaggregateTag).toHaveBeenCalledWith(1, gestern))
    expect(await screen.findByText(/PV 0,0 → 18,4 kWh/)).toBeInTheDocument()
  })

  it('bietet KEINEN Knopf, wo es nichts nachzuaggregieren gibt', async () => {
    getTagStatus.mockResolvedValue(VOR_INBETRIEBNAHME)
    renderView()

    expect(await screen.findByText(/Vor der Inbetriebnahme/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /nachrechnen/i })).not.toBeInTheDocument()
    // Der Weg zur Ursache bleibt trotzdem erreichbar.
    expect(screen.getByRole('button', { name: /Beheben/i })).toBeInTheDocument()
  })

  it('behält den vertrauten Satz, solange der Grund nicht da ist', async () => {
    getTagStatus.mockRejectedValue(new Error('offline'))
    renderView()

    expect(await screen.findByText(/Wähle einen Tag mit Messwerten/i)).toBeInTheDocument()
  })
})

/**
 * Der zweite, bis 2026-08-06 verwechselte Zustand: die Block-Liste ist leer,
 * weil **alles geparkt** ist. Dort stand „Keine Daten für diesen Tag vorhanden."
 * — das Gegenteil der Lage, denn die Werte sind da und liegen im Papierkorb.
 */
describe('Cockpit/Tag — vollständig geparkte Sicht', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _clearSwrCacheForTests()
    localStorage.clear()
    stubMatchMedia()
  })

  it('sagt, dass alles geparkt ist — nicht, dass Daten fehlen', async () => {
    const { baueTagKpis } = await import('./TagBilanz')
    const { tagBilanzParkIds } = await import('./bilanzParkIds')
    const { energieProfilApi } = await import('../api/energie_profil')
    vi.mocked(energieProfilApi.getTageWerte).mockResolvedValue([TAG_MIT_WERTEN])

    // Alle parkbaren Elemente der Sicht über die ECHTEN SoT-Ableitungen parken
    // (KPI-IDs, Bilanz-Teile, Finanz-Teaser) — Stunden und Komponenten sind leer.
    const ids = [
      ...baueTagKpis(TAG_MIT_WERTEN, null, undefined, {}).map(
        (k) => `kpi:${k.title.toLowerCase().replace(/[^a-z0-9]+/gi, '-')}`,
      ),
      ...tagBilanzParkIds(TAG_MIT_WERTEN),
      'el:finanzen-bilanz',
      'el:finanzen-link',
    ]
    localStorage.setItem(
      'eedc-park:v4-cockpit-tag',
      JSON.stringify(ids.map((id) => ({ id, titel: id }))),
    )

    renderView()

    expect(await screen.findByText(/alle Elemente dieses Tages sind geparkt/i)).toBeInTheDocument()
    expect(screen.queryByText(/Keine Daten für diesen Tag vorhanden/i)).not.toBeInTheDocument()
  })
})
