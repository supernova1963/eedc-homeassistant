/**
 * P-433-0 (Konzept #433 E12 a) — die Werte, die eedc am Feld „Betriebsmodus“
 * versteht, stehen sichtbar am Feld, mit Link auf die Werte-Tabelle im Handbuch.
 *
 * Die Liste kommt fertig aus dem Backend (`zulaessige_werte`, abgeleitet aus dem
 * Kanon `core/betriebsmodus.py`); die Fixture spiegelt deshalb die Antwortform,
 * nicht eine zweite Tabelle. Gegenprobe: ein Feld ohne `zulaessige_werte` zeigt
 * die Zeile nicht.
 *
 * P-433-2 S2 (Variante C): die Wärmepumpe ist nach Betriebsart gegliedert — der Betriebsmodus gehört
 * zum Block «Gerät gesamt» (`betriebsart: 'geraet'` aus der Registry); die Zeile steht dort.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DatenquellenZuordnung from './DatenquellenZuordnung'

vi.mock('../../api/datenquellen', () => {
  const modus = {
    id: 'inv_live_7_betriebsmodus', feld: 'betriebsmodus', typ: 'waermepumpe',
    label: 'Betriebsmodus', einheit: '', kategorie: 'live',
    hinweis: '', standard_topic: '', quelle: 'ha_app', gateway_topic: null,
    ha_entity: 'sensor.wp_prioritaet', ha_name: 'WP Priorität', zustand: true,
    invertieren: false, wert: null, wert_text: 'heating', wert_klartext: 'Unbestimmt', betriebsart: 'geraet',
    wert_zeit: null, probleme: [],
    zulaessige_werte: [
      { kanon: 'heizen', label: 'Heizen', werte: ['heat', 'heizen'] },
      { kanon: 'aus', label: 'Aus', werte: ['off', 'aus'] },
      { kanon: 'unbestimmt', label: 'Unbestimmt', werte: ['auto', 'heat_cool', 'automatik'] },
    ],
  }
  const leistung = {
    id: 'inv_live_7_leistung_w', feld: 'leistung_w', typ: 'waermepumpe',
    label: 'Leistung gesamt', einheit: 'W', kategorie: 'live',
    hinweis: '', standard_topic: '', quelle: 'ha_app', gateway_topic: null,
    ha_entity: 'sensor.wp_gesamt', ha_name: 'WP gesamt',
    invertieren: false, wert: 800, wert_zeit: null, probleme: [], zulaessige_werte: null, betriebsart: 'geraet',
  }
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        gruppen: [{ id: 'inv:7', titel: 'Wärmepumpe', typ: 'waermepumpe', felder: [modus, leistung] }],
        verfuegbarkeit: { ha: true, mqtt: false, ha_quelle: 'ha_app' },
      })),
      setQuelle: vi.fn(() => Promise.resolve()),
      setInvert: vi.fn(() => Promise.resolve()),
      haSensoren: vi.fn(() => Promise.resolve({ sensoren: [], vorschlaege: [], integrationen: [], warnungen: {} })),
      taktCheck: vi.fn(() => Promise.resolve({ geprueft: false })),
    },
  }
})

vi.mock('../../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' } }),
}))

/** Der Geräte-Block ist zugeklappt (`defaultOpen: istBasis`) — erst aufklappen. */
async function oeffneWpBlock() {
  render(<MemoryRouter><DatenquellenZuordnung /></MemoryRouter>)
  fireEvent.click(await screen.findByText(/alle aufklappen/))
}

describe('P-433-0 — zulässige Werte am Feld „Betriebsmodus“', () => {
  it('nennt die verstandenen Werte je Betriebsart, ohne Klick auf den Info-Knopf', async () => {
    await oeffneWpBlock()
    const zeile = (await screen.findByText(/eedc versteht:/)).closest('p')
    expect(zeile?.textContent).toContain('Heizen (heat, heizen)')
    expect(zeile?.textContent).toContain('Aus (off, aus)')
    expect(zeile?.textContent).toContain('als unbestimmt gezählt: auto, heat_cool, automatik')
  })

  it('verlinkt die Werte-Tabelle im Handbuch Wärme & Klima', async () => {
    await oeffneWpBlock()
    const link = await screen.findByRole('link', { name: /Werte-Tabelle im Handbuch/ })
    expect(link.getAttribute('href')).toBe('/hilfe?doc=waerme-klima#welchen-sensor-eedc-lesen-kann')
  })

  it('steht im Block «Gerät gesamt» der Wärmepumpe (Variante C)', async () => {
    await oeffneWpBlock()
    const zeile = await screen.findByText(/eedc versteht:/)
    expect(zeile.closest('[data-betriebsart]')?.getAttribute('data-betriebsart')).toBe('geraet')
  })

  it('Gegenprobe: ein Feld ohne Werte-Liste trägt die Zeile nicht', async () => {
    await oeffneWpBlock()
    await screen.findByText(/eedc versteht:/)
    expect(screen.getAllByText(/eedc versteht:/)).toHaveLength(1)
  })
})
