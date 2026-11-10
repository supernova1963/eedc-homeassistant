/**
 * E4 (1)–(3) «Daten-Checker: Sprung aufs Feld» — die Datenquellen-Fläche öffnet Block und Gerät und markiert das Feld.
 *
 * `EinstellungenV4` liest `?geraet=&feld=` (W-5) und reicht sie als `sprung` durch. Erwartet: der Typ-Block klappt auf,
 * das Gerät (eines von zweien, sonst zugeklappt) ebenso, die Feldzeile (`data-feld`) trägt den Fokus (bestehende
 * Fokus-Optik des ersten Knopfs der Zeile), «Weitere Größen erfassen» öffnet, wenn das Feld dort steht;
 * `onSprungFertig` meldet das Ende. Innengeräte-Suffix über `basisFeldKey`. Ohne Sprung bleibt alles wie bisher zu.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import DatenquellenZuordnung, { sprungZielAus } from './DatenquellenZuordnung'

vi.mock('../../api/datenquellen', () => {
  const feld = (inv: number, f: string, label: string, extra: Record<string, unknown> = {}) => ({
    id: `inv_energy_${inv}_${f}`, feld: f, typ: 'speicher', label, einheit: 'kWh', kategorie: 'energy', hinweis: '',
    standard_topic: `eedc/1/energy/inv/${inv}/${f}`, quelle: 'keine', gateway_topic: null, bedarf: 'optional',
    ha_entity: null, ha_name: null, invertieren: false, wert: null, wert_zeit: null, probleme: [], ...extra,
  })
  const geraet = (inv: number, titel: string) => ({
    id: `inv:${inv}`, titel, typ: 'speicher',
    felder: [feld(inv, 'ladung_kwh', 'Ladung'), feld(inv, 'entladung_kwh', 'Entladung'),
      feld(inv, 'ladung_netz_kwh', 'Netzladung', { erweitert: true })],
  })
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        gruppen: [geraet(7, 'Speicher Keller'), geraet(8, 'Speicher Garage')],
        verfuegbarkeit: { ha: true, mqtt: false, ha_quelle: 'ha_app' },
        historie_hinweis: null,
      })),
      setQuelle: vi.fn(() => Promise.resolve()),
      setInvert: vi.fn(() => Promise.resolve()),
    },
  }
})

vi.mock('../../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' } }),
}))

beforeEach(() => {
  localStorage.clear()
  Element.prototype.scrollIntoView = vi.fn()
})

describe('Datenquellen: Sprung aufs Gerät und Feld (E4)', () => {
  it('Gerät 8 und sein Feld: Block auf, nur dieses Gerät auf, Feldzeile fokussiert, Ende gemeldet', async () => {
    const fertig = vi.fn()
    render(<DatenquellenZuordnung sprung={{ geraet: '8', feld: 'entladung_kwh' }} onSprungFertig={fertig} />)
    await waitFor(() => expect(fertig).toHaveBeenCalledTimes(1))
    const zeile = document.querySelector('[data-feld="inv_energy_8_entladung_kwh"]')
    expect(zeile).not.toBeNull()
    expect(zeile!.contains(document.activeElement)).toBe(true)
    // Das andere Gerät bleibt zu (zwei Geräte ⇒ Default zu).
    expect(document.querySelector('[data-feld="inv_energy_7_entladung_kwh"]')).toBeNull()
  })

  it('Feld in «Weitere Größen erfassen»: der Abschnitt öffnet', async () => {
    const fertig = vi.fn()
    render(<DatenquellenZuordnung sprung={{ geraet: '7', feld: 'ladung_netz_kwh' }} onSprungFertig={fertig} />)
    await waitFor(() => expect(fertig).toHaveBeenCalled())
    expect(screen.getByText(/Netzladung/)).toBeInTheDocument()
    expect(document.querySelector('[data-feld="inv_energy_7_ladung_netz_kwh"]')!.contains(document.activeElement)).toBe(true)
  })

  it('ohne Sprung: beide Geräte zu, kein Fokus', async () => {
    render(<DatenquellenZuordnung />)
    await waitFor(() => expect(screen.queryByText('wird geladen …')).toBeNull())
    expect(document.querySelector('[data-feld^="inv_energy_"]')).toBeNull()
  })

  it('Ziel-Auflösung: Innengeräte-Suffix, Feld ohne Gerät, unbekanntes Gerät', () => {
    const g = (id: string, typ: string, felder: string[]) => ({
      id, titel: id, typ, felder: felder.map((f) => ({ id: `${id}:${f}`, feld: f })),
    }) as never
    const gruppen = [g('inv:3', 'waermepumpe', ['betriebsmodus-3', 'stromverbrauch_kwh']), g('basis', 'basis', ['netzbezug_kwh'])]
    expect(sprungZielAus(gruppen, { geraet: '3', feld: 'betriebsmodus' })?.feld?.feld).toBe('betriebsmodus-3')
    expect(sprungZielAus(gruppen, { feld: 'netzbezug_kwh' })?.gruppe.id).toBe('basis')
    expect(sprungZielAus(gruppen, { geraet: '9', feld: 'x' })).toBeNull()
    expect(sprungZielAus(gruppen, { geraet: '3' })?.feld).toBeNull()
  })
})
