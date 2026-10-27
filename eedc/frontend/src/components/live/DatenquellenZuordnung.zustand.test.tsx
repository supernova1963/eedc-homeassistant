/**
 * Datenquellen — Abschnitt «Zustand & Sitzung» an Wallbox und E-Auto (P-433-2b K1, Bauplan E4).
 *
 * Die Felder tragen das Registry-Attribut `abschnitt: 'zustand'` (nicht aus der Einheit geraten — die kWh der Sitzung
 * ist kein Zähler der Bilanz). Der Kopf sagt, was die Zuordnung ermöglicht («Zustands-Chip: zugeordnet / fehlt»,
 * #431-Prinzip); die Werte-Tabelle am Zustandsfeld nennt «Andere Werte zeigt eedc nicht an» und verlinkt das Handbuch
 * Einstellungen. Unzugeordnete Felder bleiben hinter «Weitere Größen erfassen» (R1).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DatenquellenZuordnung, { TEXT_LEER, zustandsChipStatus } from './DatenquellenZuordnung'
import type { DatenquelleFeld } from '../../api/datenquellen'

vi.mock('../../api/datenquellen', () => {
  let n = 0
  const feld = (gid: string, feld: string, label: string, einheit: string, extra: Record<string, unknown> = {}) => ({
    id: `${gid}_${feld}_${n++}`, feld, typ: 'x', label, einheit, kategorie: 'live',
    hinweis: `Hinweis zu ${label}`, standard_topic: `eedc/1/${gid}/${feld}`,
    quelle: 'keine', gateway_topic: null, ha_entity: null, ha_name: null,
    invertieren: false, wert: null, wert_zeit: null, probleme: [],
    bedarf: 'optional', bedarf_grund: null, bedarf_text: null, ausgewertet_in: [],
    ...extra,
  })
  const zs = { abschnitt: 'zustand' }
  const gruppen = [
    { id: 'inv:4', titel: 'SMA eCharger 22', typ: 'wallbox', felder: [
      feld('inv4', 'leistung_w', 'Leistung', 'W', { quelle: 'ha_app', ha_entity: 'sensor.wb', wert: 7400 }),
      feld('inv4', 'ladezustand', 'Ladezustand', '', {
        ...zs, zustand: true, quelle: 'ha_app', ha_entity: 'sensor.wallbox_status_ladevorgang',
        wert_text: 'active_mode', wert_klartext: 'Lädt',
        zulaessige_werte: [{ kanon: 'laedt', label: 'Lädt', werte: ['laedt', 'active_mode'] }],
      }),
      // P-433-2b K2a: das Textfeld — leer über MQTT angekommen («die Steuerung kennt kein Fahrzeug»).
      feld('inv4', 'fahrzeug_am_ladepunkt', 'Fahrzeug am Ladepunkt', '', {
        ...zs, zustand: true, quelle: 'mqtt_inbound_standard', wert_text: '', wert_klartext: null, zulaessige_werte: null,
      }),
      feld('inv4', 'sitzung_kwh', 'Energie dieser Sitzung', 'kWh', { ...zs, quelle: 'ha_app', ha_entity: 'sensor.s', wert: 9.8 }),
      feld('inv4', 'ladestrom_a', 'Ladestrom', 'A', { ...zs, erweitert: true }),
    ] },
    { id: 'inv:5', titel: 'Smart #1', typ: 'e-auto', felder: [
      feld('inv5', 'soc', 'Ladestand', '%', { quelle: 'ha_app', ha_entity: 'sensor.smart_batterie', wert: 62 }),
      feld('inv5', 'ladezustand_fahrzeug', 'Ladezustand (Fahrzeug)', '', { ...zs, zustand: true, erweitert: true }),
      feld('inv5', 'reichweite_km', 'Reichweite', 'km', { ...zs, quelle: 'ha_app', ha_entity: 'sensor.smart_reichweite', wert: 312 }),
    ] },
  ]
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        anlage_id: 1, gruppen, verfuegbarkeit: { ha: true, mqtt: true, ha_quelle: 'ha_app' }, historie_hinweis: null,
      })),
      setQuelle: vi.fn(() => Promise.resolve({ historie_hinweis: null })),
      setInvert: vi.fn(() => Promise.resolve({ historie_hinweis: null })),
      haSensoren: vi.fn(() => Promise.resolve({ sensoren: [], vorschlaege: [], integrationen: [], warnungen: {} })),
      taktCheck: vi.fn(() => Promise.resolve({ geprueft: false })),
    },
  }
})

vi.mock('../../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' } }),
}))

describe('P-433-2b K1 — Datenquellen «Zustand & Sitzung»', () => {
  it('Abschnitt mit Kopf-Status, kWh der Sitzung nicht unter «Energie-Sensoren», Werte-Tabelle der E-Mobilität', async () => {
    localStorage.clear()
    const { container } = render(<MemoryRouter><DatenquellenZuordnung /></MemoryRouter>)
    fireEvent.click(await screen.findByText(/alle aufklappen/))
    const status = [...container.querySelectorAll('[data-zustand-status]')].map((s) => s.textContent)
    expect(status).toEqual(['Zustands-Chip: zugeordnet', 'Zustands-Chip: fehlt'])
    expect(container.textContent).toContain('Zustand & Sitzung')
    expect(container.textContent).not.toContain('Energie-Sensoren (kWh)')
    expect(container.textContent).toContain('Lädt (active_mode)')
    expect(container.textContent).toContain('Andere Werte zeigt eedc nicht an')
    const link = [...container.querySelectorAll('a')].find((a) => a.textContent === 'Werte-Tabelle im Handbuch')!
    expect(link.getAttribute('href')).toContain('doc=einstellungen')
    // R1: das unzugeordnete Feld wartet hinter «Weitere Größen erfassen».
    expect(screen.getAllByRole('button', { name: /Weitere Größen erfassen/ }).length).toBe(2)
  })

  it('P-433-2b K2a: ein leer angekommener Text heißt «(leer)», keine leere grüne Zelle; der Kopf bleibt beim Ladezustand', async () => {
    localStorage.clear()
    const { container } = render(<MemoryRouter><DatenquellenZuordnung /></MemoryRouter>)
    fireEvent.click(await screen.findByText(/alle aufklappen/))
    expect(container.textContent).toContain(TEXT_LEER)
    expect([...container.querySelectorAll('[data-zustand-status]')].map((s) => s.textContent)[0]).toBe('Zustands-Chip: zugeordnet')
  })

  it('zustandsChipStatus: ohne Zustandsfeld nichts', () => {
    const f = (x: Partial<DatenquelleFeld>) => x as DatenquelleFeld
    expect(zustandsChipStatus([f({ abschnitt: 'zustand', zustand: false, quelle: 'ha_app' })])).toBeNull()
    expect(zustandsChipStatus([f({ zustand: true, quelle: 'ha_app' })])).toBeNull()
  })
})
