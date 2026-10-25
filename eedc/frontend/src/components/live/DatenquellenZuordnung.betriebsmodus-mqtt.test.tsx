/**
 * HA-Bauform §9 (Standalone-Gleichstand S1, S1-3) — der Betriebsmodus über MQTT-Inbound auf der Zuordnungs-Fläche.
 *
 * Das Backend liefert für ein Zustandsfeld über Inbound `wert: null` und den rohen Text in `wert_text`
 * (`api/routes/datenquellen.py`, Ü1). Die Fläche zeigt dann Klartext und Rohwert — keine Zahl. Läge der String in
 * `wert`, rundete die Fläche ihn (`Math.round(f.wert * 100) / 100`) und zeigte «NaN»: diese Probe wird dann rot.
 * Dazu: der Inbound-Knopf steht am Feld, der Gateway-Knopf nicht (das Gateway reicht nur Zahlen weiter).
 * Die Fixture spiegelt die Antwortform des Backends, keine zweite Tabelle.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DatenquellenZuordnung from './DatenquellenZuordnung'

vi.mock('../../api/datenquellen', () => {
  const modus = {
    id: 'inv_live_7_betriebsmodus', feld: 'betriebsmodus', typ: 'waermepumpe',
    label: 'Betriebsmodus', einheit: '', kategorie: 'live',
    hinweis: '', standard_topic: 'eedc/1_Test/live/inv/7_WP/betriebsmodus', quelle: 'mqtt_inbound_standard',
    gateway_topic: null, ha_entity: null, ha_name: null, zustand: true, nur_ha: false,
    invertieren: false, wert: null, wert_text: 'warmwasser', wert_klartext: 'Warmwasser', betriebsart: 'geraet',
    wert_zeit: null, probleme: [], zulaessige_werte: null,
  }
  const leistung = {
    id: 'inv_live_7_leistung_w', feld: 'leistung_w', typ: 'waermepumpe',
    label: 'Leistung gesamt', einheit: 'W', kategorie: 'live',
    hinweis: '', standard_topic: 'eedc/1_Test/live/inv/7_WP/leistung_w', quelle: 'mqtt_inbound_standard',
    gateway_topic: null, ha_entity: null, ha_name: null, nur_ha: false,
    invertieren: false, wert: 812.345, wert_zeit: null, probleme: [], zulaessige_werte: null, betriebsart: 'geraet',
  }
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        gruppen: [{ id: 'inv:7', titel: 'Wärmepumpe', typ: 'waermepumpe', felder: [modus, leistung] }],
        verfuegbarkeit: { ha: false, mqtt: true, ha_quelle: null },
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

async function oeffneWpBlock() {
  render(<MemoryRouter><DatenquellenZuordnung /></MemoryRouter>)
  fireEvent.click(await screen.findByText(/alle aufklappen/))
}

/** Die Feld-Zeile der Zuordnung, die das Label trägt — die Topic-Liste daneben nennt dasselbe Label ohne Knöpfe. */
async function zeileVon(label: string): Promise<HTMLElement> {
  const spans = await screen.findAllByText(label, { selector: 'span' })
  const zeilen = spans
    .map((s) => s.closest('div.flex.flex-col') as HTMLElement | null)
    .filter((z): z is HTMLElement => !!z && !!within(z).queryByRole('button', { name: 'Keine' }))
  if (zeilen.length !== 1) throw new Error(`Feld-Zeile für ${label}: ${zeilen.length} Treffer`)
  return zeilen[0]
}

describe('HA-Bauform §9 — Betriebsmodus über MQTT-Inbound', () => {
  it('zeigt Klartext und Rohwert, keine Zahl und kein «NaN»', async () => {
    await oeffneWpBlock()
    const zeile = await zeileVon('Betriebsmodus')
    expect(zeile.textContent).toContain('Warmwasser')
    expect(zeile.textContent).not.toContain('NaN')
    expect(document.body.textContent).not.toContain('NaN')
  })

  it('bietet Inbound an, das Gateway nicht', async () => {
    await oeffneWpBlock()
    const zeile = await zeileVon('Betriebsmodus')
    expect(within(zeile).getByRole('button', { name: 'Inbound' })).toBeTruthy()
    expect(within(zeile).queryByRole('button', { name: 'Gateway' })).toBeNull()
  })

  it('Gegenprobe: ein Zahlenfeld behält beide MQTT-Knöpfe und seine gerundete Zahl', async () => {
    await oeffneWpBlock()
    const zeile = await zeileVon('Leistung gesamt (W)')
    expect(within(zeile).getByRole('button', { name: 'Inbound' })).toBeTruthy()
    expect(within(zeile).getByRole('button', { name: 'Gateway' })).toBeTruthy()
    expect(zeile.textContent).toContain('812.35 W')
  })
})
