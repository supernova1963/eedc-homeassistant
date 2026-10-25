/**
 * Datenquellen-Zuordnung einer Wärmepumpe nach Betriebsart (P-433-2 S2, Variante C #431).
 *
 * Die Fläche gliedert eine Wärmepumpe in Blöcke «Gerät gesamt» · «Heizen» · «Warmwasser» · «Kühlen» …
 * mit Status im Kopf; die Feld-Zeile ist dieselbe wie überall, erweiterte Felder bleiben in
 * «Weitere Größen erfassen». Die Fälle kommen aus der Route (`src/test/datenquellen-wp-faelle.json`).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DatenquellenZuordnung from './DatenquellenZuordnung'
import { gruppeAusFall, type WpFall } from '../../test/datenquellenWpFaelle'
import type { DatenquelleGruppe } from '../../api/datenquellen'
import { funktionsKopf } from '../../lib/funktionsFarben'

const lage = vi.hoisted(() => ({ gruppen: [] as unknown[] }))

vi.mock('../../api/datenquellen', () => ({
  VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
  datenquellenApi: {
    getFelder: vi.fn(() => Promise.resolve({
      anlage_id: 1, gruppen: lage.gruppen, verfuegbarkeit: { ha: true, mqtt: false, ha_quelle: 'ha_app' }, historie_hinweis: null,
    })),
    setQuelle: vi.fn(() => Promise.resolve({ historie_hinweis: null })),
    setInvert: vi.fn(() => Promise.resolve({ historie_hinweis: null })),
    haSensoren: vi.fn(() => Promise.resolve({ sensoren: [], vorschlaege: [], integrationen: [], warnungen: {} })),
    taktCheck: vi.fn(() => Promise.resolve({ geprueft: false })),
  },
}))

vi.mock('../../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' } }),
}))

const VORRANG = 'Betriebsart-Zähler; hat Vorrang vor „Strom Heizen“. Wer getrennt misst, lässt dieses Feld leer.'

async function zeige(fall: WpFall, anpassen?: (g: DatenquelleGruppe) => void) {
  const g = gruppeAusFall(fall)
  anpassen?.(g)
  lage.gruppen = [g]
  localStorage.clear()
  const r = render(<MemoryRouter><DatenquellenZuordnung /></MemoryRouter>)
  fireEvent.click(await screen.findByText(/alle aufklappen/))
  return r
}

function block(container: HTMLElement, betriebsart: string): HTMLElement | null {
  return container.querySelector(`[data-betriebsart="${betriebsart}"]`)
}

describe('P-433-2 S2 — Wärmepumpe nach Betriebsart', () => {
  beforeEach(() => { lage.gruppen = [] })

  it('Mathek: Blöcke mit Status, keine Abschnitte nach Einheit', async () => {
    const { container } = await zeige('mathek')
    const titel = [...container.querySelectorAll('[data-betriebsart]')].map((b) => b.getAttribute('data-betriebsart'))
    expect(titel).toEqual(['geraet', 'heizen', 'warmwasser', 'kuehlen'])
    const status = (b: string) => block(container, b)?.querySelector('[data-blockstatus]')?.textContent
    expect(status('heizen')).toBe('● vollständig')
    expect(status('warmwasser')).toBe('● vollständig')
    expect(status('kuehlen')).toBe('passiv')
    expect(screen.queryByText('Energie-Sensoren (kWh)')).toBeNull()
    expect(screen.queryByText('Leistung-Sensoren (W)')).toBeNull()
  })

  it('Mathek: Felder stehen im Block ihrer Betriebsart, mit derselben Zeile (Quelle, Knöpfe)', async () => {
    const { container } = await zeige('mathek')
    const heizen = within(block(container, 'heizen')!)
    expect(heizen.getByText('Strom Heizen (kWh)')).toBeInTheDocument()
    expect(heizen.getByText('Heizwärme (kWh)')).toBeInTheDocument()
    expect(heizen.getAllByRole('button', { name: 'HA-Sensor' }).length).toBeGreaterThan(0)
    const ww = within(block(container, 'warmwasser')!)
    expect(ww.getByText('Warmwasser-Temperatur (°C)')).toBeInTheDocument()
    // Ein kühlendes Gerät (hier passiv) hat die Kühl-Zähler in der ersten Reihe (Registry `kuehlt`).
    const kuehlen = within(block(container, 'kuehlen')!)
    expect(kuehlen.getByText('Strom Kühlbetrieb (kWh)')).toBeInTheDocument()
    expect(kuehlen.getByText('Leistung Kühlen (W)')).toBeInTheDocument()
  })

  it('erweiterte Felder bleiben in «Weitere Größen erfassen» und klappen dort auf', async () => {
    const { container } = await zeige('mathek')
    expect(container.textContent).not.toContain('Strom Lüftbetrieb')
    fireEvent.click(screen.getByRole('button', { name: /Weitere Größen erfassen \(7\)/ }))
    expect(screen.getByText('Strom Lüftbetrieb (kWh)')).toBeInTheDocument()
    expect(screen.getByText('Stromverbrauch (kWh)')).toBeInTheDocument()
  })

  it('pipp086: der Betriebsart-Zähler steht im Block Heizen, sein Hinweis nennt den Vorrang', async () => {
    const { container } = await zeige('pipp086', (g) => {
      const f = g.felder.find((x) => x.feld === 'betriebsart_strom_heizen_kwh')!
      f.hinweis = `${VORRANG} Elektrische Energie …`
    })
    const heizen = within(block(container, 'heizen')!)
    expect(heizen.getByText('Strom Heizbetrieb (kWh)')).toBeInTheDocument()
    const zeile = heizen.getByText('Strom Heizbetrieb (kWh)').closest('div.flex.flex-col') as HTMLElement
    fireEvent.click(within(zeile).getByRole('button', { name: 'Hinweis anzeigen' }))
    expect(within(zeile).getByText(/hat Vorrang vor „Strom Heizen“/)).toBeInTheDocument()
    expect(block(container, 'heizen')?.querySelector('[data-blockstatus]')?.textContent).toBe('⊘ fehlt: Wärme')
  })

  it('Sole passiv ohne Kühlzähler: Kühlen erscheint mit Kopf «passiv»; luft_wasser ohne Kühlung hat keinen Kühlen-Block', async () => {
    const r = await zeige('sole_passiv_ohne_kuehlfeld')
    expect(block(r.container, 'kuehlen')?.querySelector('[data-blockstatus]')?.textContent).toBe('passiv')
    r.unmount()
    const r2 = await zeige('luft_wasser')
    expect(block(r2.container, 'kuehlen')).toBeNull()
    expect(block(r2.container, 'lueften')).toBeNull()
  })

  it('Brauchwasser ohne Heizen-Block, Klimaanlage ohne Warmwasser-Block — ihre Felder unter «Weitere Größen»', async () => {
    const r = await zeige('brauchwasser')
    expect(block(r.container, 'heizen')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Weitere Größen erfassen/ }))
    expect(screen.getByText('Leistung Heizen (W)')).toBeInTheDocument()
    r.unmount()
    const r2 = await zeige('luft_luft')
    expect(block(r2.container, 'warmwasser')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Weitere Größen erfassen/ }))
    expect(screen.getByText('Warmwasser-Temperatur (°C)')).toBeInTheDocument()
  })
})

describe('P-433-2c C-6 — Gestalt nach Mockup «Datenquellen Wärmepumpe Variante C»', () => {
  beforeEach(() => { lage.gruppen = [] })

  it('jeder Block ist eine Karte mit getönter Kopfzeile in der Farbe seiner Betriebsart; «Gerät gesamt» neutral', async () => {
    const { container } = await zeige('mathek')
    const kopf = (b: string) => block(container, b)!.querySelector('[data-block-kopf]')!
    expect(block(container, 'heizen')!.getAttribute('data-block')).toBe('heizen')
    expect(kopf('geraet').className).toContain(funktionsKopf('geraet'))
    expect(funktionsKopf('geraet')).toMatch(/bg-gray-50/)
    for (const b of ['heizen', 'warmwasser', 'kuehlen']) {
      expect(kopf(b).className, b).toContain(funktionsKopf(b))
      expect(funktionsKopf(b), b).not.toBe(funktionsKopf('geraet'))
    }
    // Die Karte ist die Card-SoT (Rahmen), Titel links, Status rechts im Kopf.
    expect(block(container, 'heizen')!.parentElement!.className).toContain('rounded-xl')
    expect(kopf('heizen').querySelector('[data-blockstatus]')!.textContent).toBe('● vollständig')
    expect(kopf('kuehlen').querySelector('[data-blockstatus]')!.textContent).toBe('passiv')
  })

  it('Fußzeile unter den Blöcken mit dem Weg zur Investition, vor «Weitere Größen erfassen»', async () => {
    const { container } = await zeige('mathek')
    const fuss = container.querySelector('[data-betriebsart-fusszeile]')!
    expect(fuss.textContent).toBe('Welche Betriebsarten ein Gerät hat (Heizen, Warmwasser, Kühlen, Lüften …), folgt aus der Investition: '
      + 'Art und Funktionen unter Investition bearbeiten. Hier werden nur Sensoren zugeordnet.')
    expect(fuss.querySelector('a')!.getAttribute('href')).toBe('#/einstellungen/komponenten?bearbeiten=5')
    const letzterBlock = [...container.querySelectorAll('[data-block]')].at(-1)!
    expect(letzterBlock.compareDocumentPosition(fuss) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    const weitere = screen.queryByText(/Weitere Größen erfassen/)
    if (weitere) expect(fuss.compareDocumentPosition(weitere) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})
