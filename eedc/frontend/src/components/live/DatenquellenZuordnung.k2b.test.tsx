/**
 * P-433-2b K2b (Bauplan K2 §1 K2-7/K2-8, §3b E1/E2, Entscheid D3) — Datenquellen: Gateway am Zustandsfeld, Option A.
 *
 * - Das Gateway reicht an ein Zustandsfeld den Text weiter (Weiche am Zielfeld im Backend) — der Gateway-Knopf steht
 *   deshalb auch an «Lademodus» und an den evcc-Rollen-Feldern; **am Betriebsmodus bleibt er aus** (D3, Sprengsatz
 *   S11), auch an `betriebsmodus-3` (Innengeräte-Suffix).
 * - Der Kopf «Zustand & Sitzung» sagt «zugeordnet (aus connected/charging/enabled)», wenn kein Ladezustand, aber
 *   «evcc: Fahrzeug verbunden» eine Quelle hat (Option A).
 * - Der Gateway-Picker blendet an einem Zustandsfeld Faktor/Offset aus, fragt die Vorschau mit `als_text` und zeigt
 *   den Text (`wert_text`); gespeichert wird neutral (Faktor 1, Offset 0).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DatenquellenZuordnung, { istModusFeld, zustandsChipStatus } from './DatenquellenZuordnung'
import DatenquellenGatewayPicker from './DatenquellenGatewayPicker'
import type { DatenquelleFeld } from '../../api/datenquellen'
import { liveDashboardApi } from '../../api/liveDashboard'

vi.mock('../../api/datenquellen', () => {
  let n = 0
  const feld = (gid: string, feld: string, label: string, einheit: string, extra: Record<string, unknown> = {}) => ({
    id: `${gid}_${feld}_${n++}`, feld, typ: 'x', label, einheit, kategorie: 'live',
    hinweis: '', standard_topic: `eedc/1/${gid}/${feld}`,
    quelle: 'keine', gateway_topic: null, ha_entity: null, ha_name: null,
    invertieren: false, wert: null, wert_zeit: null, probleme: [],
    bedarf: 'optional', bedarf_grund: null, bedarf_text: null, ausgewertet_in: [],
    ...extra,
  })
  const zs = { abschnitt: 'zustand', zustand: true }
  const gruppen = [
    { id: 'inv:4', titel: 'evcc Carport', typ: 'wallbox', felder: [
      feld('inv4', 'leistung_w', 'Leistung', 'W', { quelle: 'mqtt_inbound_standard', wert: 7400 }),
      feld('inv4', 'ladezustand', 'Ladezustand', '', zs),
      feld('inv4', 'lademodus', 'Lademodus', '', { ...zs, quelle: 'mqtt_gateway', gateway_topic: 'evcc/loadpoints/1/mode',
        wert_text: 'now', wert_klartext: 'Schnell' }),
      feld('inv4', 'evcc_verbunden', 'evcc: Fahrzeug verbunden', '', {
        ...zs, quelle: 'ha_app', ha_entity: 'binary_sensor.evcc_carport_connected', wert_text: 'on', wert_klartext: 'Verbunden',
      }),
    ] },
    { id: 'inv:7', titel: 'Klima', typ: 'waermepumpe', felder: [
      feld('inv7', 'betriebsmodus-3', 'Betriebsmodus Büro', '', { zustand: true, quelle: 'mqtt_inbound_standard' }),
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
      level: vi.fn(() => Promise.resolve({
        children: [{ segment: 'mode', has_children: false,
          leaf: { topic: 'evcc/loadpoints/1/mode', payload_sample: ' now ', payload_typ: 'plain', wert: null } }],
        self_leaf: null, begrenzt: false,
      })),
    },
  }
})

vi.mock('../../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' } }),
}))

async function zeileVon(label: string): Promise<HTMLElement> {
  const spans = await screen.findAllByText(label, { selector: 'span' })
  const zeilen = spans
    .map((s) => s.closest('div.flex.flex-col') as HTMLElement | null)
    .filter((z): z is HTMLElement => !!z && !!within(z).queryByRole('button', { name: 'Keine' }))
  if (zeilen.length !== 1) throw new Error(`Feld-Zeile für ${label}: ${zeilen.length} Treffer`)
  return zeilen[0]
}

describe('P-433-2b K2b — Gateway am Zustandsfeld, D3', () => {
  it('Gateway-Knopf an Lademodus und evcc-Rollen-Feld, nicht am Betriebsmodus (auch mit Suffix)', async () => {
    localStorage.clear()
    render(<MemoryRouter><DatenquellenZuordnung /></MemoryRouter>)
    fireEvent.click(await screen.findByText(/alle aufklappen/))
    expect(within(await zeileVon('Lademodus')).getByRole('button', { name: 'Gateway' })).toBeTruthy()
    expect(within(await zeileVon('evcc: Fahrzeug verbunden')).getByRole('button', { name: 'Gateway' })).toBeTruthy()
    const modus = await zeileVon('Betriebsmodus Büro')
    expect(within(modus).queryByRole('button', { name: 'Gateway' })).toBeNull()
    expect(within(modus).getByRole('button', { name: 'Inbound' })).toBeTruthy()
  })

  it('istModusFeld: nur der Betriebsmodus, mit und ohne Innengeräte-Suffix', () => {
    expect(istModusFeld('betriebsmodus')).toBe(true)
    expect(istModusFeld('betriebsmodus-3')).toBe(true)
    expect(istModusFeld('lademodus')).toBe(false)
    expect(istModusFeld('evcc_verbunden')).toBe(false)
  })
})

describe('P-433-2b K2b — Option A im Kopf «Zustand & Sitzung»', () => {
  const f = (x: Partial<DatenquelleFeld>) => ({ abschnitt: 'zustand', ...x }) as DatenquelleFeld

  it('ohne Ladezustand, aber mit «evcc: Fahrzeug verbunden» ⇒ zugeordnet (aus connected/charging/enabled)', async () => {
    localStorage.clear()
    const { container } = render(<MemoryRouter><DatenquellenZuordnung /></MemoryRouter>)
    fireEvent.click(await screen.findByText(/alle aufklappen/))
    const status = [...container.querySelectorAll('[data-zustand-status]')].map((s) => s.textContent)
    expect(status[0]).toBe('Zustands-Chip: zugeordnet (aus connected/charging/enabled)')
  })

  it('ein Ladezustand geht vor; ohne beides «fehlt»', () => {
    const lz = (quelle: string) => f({ feld: 'ladezustand', zustand: true, quelle })
    const ev = (quelle: string) => f({ feld: 'evcc_verbunden', zustand: true, quelle })
    expect(zustandsChipStatus([lz('ha_app'), ev('ha_app')])).toBe('Zustands-Chip: zugeordnet')
    expect(zustandsChipStatus([lz('keine'), ev('mqtt_gateway')])).toBe('Zustands-Chip: zugeordnet (aus connected/charging/enabled)')
    expect(zustandsChipStatus([lz('keine'), ev('keine')])).toBe('Zustands-Chip: fehlt')
    expect(zustandsChipStatus([lz('keine')])).toBe('Zustands-Chip: fehlt')
  })
})

describe('P-433-2b K2b — Gateway-Picker am Zustandsfeld', () => {
  it('ohne Faktor/Offset, Vorschau als Text, speichert neutral', async () => {
    const vorschau = vi.spyOn(liveDashboardApi, 'testGatewayTransform')
      .mockResolvedValue({ erfolg: true, wert_text: 'now', ziel_payload: 'now' })
    const onSpeichern = vi.fn()
    render(
      <DatenquellenGatewayPicker isOpen anlageId={1} feldLabel="Lademodus" zustand
        initialTopic="evcc/loadpoints/1/mode" onClose={() => {}} onSpeichern={onSpeichern} />,
    )
    await screen.findByText('evcc/loadpoints/1/mode', { selector: 'div' })
    expect(screen.queryByText('Faktor')).toBeNull()
    expect(screen.queryByText('Offset')).toBeNull()
    expect(screen.getByRole('option', { name: 'Text (plain)' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Vorschau berechnen' }))
    await waitFor(() => expect(document.querySelector('[data-vorschau-text]')?.textContent).toBe('Ergebnis: now'))
    expect(vorschau.mock.calls[0][0]).toMatchObject({ als_text: true, payload: ' now ' })
    fireEvent.click(screen.getByRole('button', { name: 'Quelle speichern' }))
    expect(onSpeichern).toHaveBeenCalledWith(expect.objectContaining({ faktor: 1, offset: 0, quell_topic: 'evcc/loadpoints/1/mode' }))
    vorschau.mockRestore()
  })

  it('leerer Text heißt «(leer)»; ein Zahlenfeld behält Faktor/Offset und fragt ohne Text', async () => {
    const vorschau = vi.spyOn(liveDashboardApi, 'testGatewayTransform')
      .mockResolvedValue({ erfolg: true, wert_text: '', ziel_payload: '' })
    const { unmount } = render(
      <DatenquellenGatewayPicker isOpen anlageId={1} feldLabel="Fahrzeug" zustand
        initialTopic="evcc/loadpoints/1/mode" onClose={() => {}} onSpeichern={() => {}} />,
    )
    await screen.findByText('evcc/loadpoints/1/mode', { selector: 'div' })
    fireEvent.click(screen.getByRole('button', { name: 'Vorschau berechnen' }))
    await waitFor(() => expect(document.querySelector('[data-vorschau-text]')?.textContent).toBe('Ergebnis: (leer)'))
    unmount()
    vorschau.mockResolvedValue({ erfolg: true, wert: 1.5, ziel_payload: '1.5' })
    render(
      <DatenquellenGatewayPicker isOpen anlageId={1} feldLabel="Leistung (W)"
        initialTopic="evcc/loadpoints/1/mode" onClose={() => {}} onSpeichern={() => {}} />,
    )
    await screen.findByText('evcc/loadpoints/1/mode', { selector: 'div' })
    expect(screen.getByText('Faktor')).toBeTruthy()
    expect(screen.getByText('Offset')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Vorschau berechnen' }))
    await waitFor(() => expect(vorschau).toHaveBeenCalledTimes(2))
    expect(vorschau.mock.calls[1][0]).toMatchObject({ als_text: false })
    vorschau.mockRestore()
  })
})
