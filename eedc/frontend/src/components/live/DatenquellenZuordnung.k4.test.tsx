/**
 * P-433-2b K4 (Bauplan K4-7/K4-8) — «Preset anwenden …» in der Datenquellen-Fläche.
 *
 * - Der Knopf steht an einem Gerät nur, wenn ein Geräte-Preset den Typ trägt (`MqttPreset.typen` aus dem Backend, keine
 *   zweite Tabelle im Client) — an der Wallbox ja, an der Wärmepumpe nein; an der Anlage für Presets ohne Gerät.
 * - Der Dialog belegt die Variablen mit ihrer Vorgabe, zeigt die Zeilen, sagt «werden ersetzt», wendet mit der
 *   Investition an und lädt die Felder neu.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DatenquellenZuordnung from './DatenquellenZuordnung'
import { ERSETZEN_HINWEIS, presetsFuerAnlage, presetsFuerTyp, topicVorschau } from './DatenquellenPresetDialog'
import { datenquellenApi } from '../../api/datenquellen'
import { liveDashboardApi, type MqttPreset } from '../../api/liveDashboard'

vi.mock('../../api/datenquellen', () => {
  const feld = (gid: string, feld: string, label: string) => ({
    id: `${gid}_${feld}`, feld, typ: 'x', label, einheit: 'W', kategorie: 'live',
    hinweis: '', standard_topic: `eedc/1/${gid}/${feld}`,
    quelle: 'keine', gateway_topic: null, ha_entity: null, ha_name: null,
    invertieren: false, wert: null, wert_zeit: null, probleme: [],
    bedarf: 'optional', bedarf_grund: null, bedarf_text: null, ausgewertet_in: [],
  })
  const gruppen = [
    { id: 'basis', titel: 'Anlage / Zähler', typ: 'basis', felder: [feld('basis', 'netzbezug_w', 'Netzbezug')] },
    { id: 'inv:4', titel: 'Carport', typ: 'wallbox', felder: [feld('inv4', 'leistung_w', 'Leistung')] },
    { id: 'inv:7', titel: 'Klima', typ: 'waermepumpe', felder: [feld('inv7', 'leistung_w', 'Leistung WP')] },
  ]
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        anlage_id: 1, gruppen, verfuegbarkeit: { ha: false, mqtt: true, ha_quelle: null },
      })),
      pruefeQuelle: vi.fn(() => Promise.resolve({ grund_erforderlich: false })),
      korrekturLaeufe: vi.fn(() => Promise.resolve([])),
      wartendeWechsel: vi.fn(() => Promise.resolve([])),
      korrekturLauf: vi.fn(() => Promise.resolve({
        lauf: 'L7', sensor_key: 'inv:4:ladung_kwh', status: 'laeuft', tage: 9, erledigt: 2, fehler: [], beginn: null,
        ende: null, fuellen_offen: false })),
      setQuelle: vi.fn(() => Promise.resolve({ korrektur: [] })),
      taktCheck: vi.fn(() => Promise.resolve({ geprueft: false })),
    },
  }
})

vi.mock('../../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' } }),
}))

const PRESETS: MqttPreset[] = [
  {
    id: 'evcc_ladepunkt', name: 'evcc Ladepunkt', hersteller: 'evcc', gruppe: 'Wallbox', beschreibung: 'Ladepunkt',
    anleitung: 'evcc MQTT aktivieren', erfordert_investition: true, typen: ['wallbox'],
    variablen: [
      { key: 'prefix', label: 'Prefix', placeholder: 'evcc', hinweis: '', vorgabe: 'evcc' },
      { key: 'loadpoint', label: 'Ladepunkt', placeholder: '1', hinweis: '', vorgabe: '1' },
    ],
    mappings: [{ topic_template: '{prefix}/loadpoints/{loadpoint}/chargePower', ziel_key: 'live/inv/{inv_id}/leistung_w',
      beschreibung: 'Ladeleistung', payload_typ: 'plain', json_pfad: null, faktor: 1, invertieren: false }],
  },
  {
    id: 'opendtu', name: 'OpenDTU', hersteller: 'OpenDTU', gruppe: 'Solar / WR', beschreibung: 'PV', anleitung: '',
    erfordert_investition: false, typen: [], variablen: [], mappings: [],
  },
]

describe('P-433-2b K4 — Preset anwenden', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(liveDashboardApi, 'getGatewayPresets').mockResolvedValue(PRESETS)
  })

  it('Preset-Knopf nur bei passendem Typ: Wallbox ja, Wärmepumpe nein, Anlage ja', async () => {
    const { container } = render(<MemoryRouter><DatenquellenZuordnung /></MemoryRouter>)
    fireEvent.click(await screen.findByText(/alle aufklappen/))
    await waitFor(() => expect(container.querySelector('[data-preset-knopf="4"]')).not.toBeNull())
    expect(container.querySelector('[data-preset-knopf="7"]')).toBeNull()
    expect(container.querySelector('[data-preset-knopf="anlage"]')).not.toBeNull()
  })

  it('Anwenden mit Vorgaben und Investition, danach lädt die Fläche neu', async () => {
    vi.spyOn(liveDashboardApi, 'pruefeGatewayPreset').mockResolvedValue({ grund_erforderlich: false, felder: [] })
    const apply = vi.spyOn(liveDashboardApi, 'applyGatewayPreset').mockResolvedValue(
      { preset_id: 'evcc_ladepunkt', erstellt: 1, mappings: [], ersetzt: 0, quelle_gesetzt: 1, ohne_feld: [] })
    const { container } = render(<MemoryRouter><DatenquellenZuordnung /></MemoryRouter>)
    fireEvent.click(await screen.findByText(/alle aufklappen/))
    await waitFor(() => expect(container.querySelector('[data-preset-knopf="4"]')).not.toBeNull())
    const vorher = vi.mocked(datenquellenApi.getFelder).mock.calls.length
    fireEvent.click(container.querySelector('[data-preset-knopf="4"]') as HTMLElement)
    const dialog = await waitFor(() => document.querySelector('[data-preset-dialog]') as HTMLElement)
    // Ein Preset ⇒ gleich gewählt; Vorschau mit den Vorgaben, Hinweis «ersetzt».
    expect(dialog.querySelector('[data-preset-vorschau]')?.textContent).toContain('evcc/loadpoints/1/chargePower')
    expect(dialog.textContent).toContain(ERSETZEN_HINWEIS)
    fireEvent.click(dialog.querySelector('[data-preset-anwenden]') as HTMLElement)
    await waitFor(() => expect(apply).toHaveBeenCalledWith(
      { preset_id: 'evcc_ladepunkt', anlage_id: 1, variablen: {}, investition_id: 4 }))
    await waitFor(() => expect(vi.mocked(datenquellenApi.getFelder).mock.calls.length).toBe(vorher + 1))
  })

  it('Sensorwechsel S3b: fragt das Preset einen Grund, öffnet der Dialog — angewendet wird erst mit dem Grund', async () => {
    const frage = {
      grund_erforderlich: true, erster_wert: null, tage: 649, stand_alt: 1.0, stand_neu: null,
      sensor_key: 'inv:4:ladung_kwh', label: 'Ladung', verzeichnet: true, korrektur: null,
    }
    vi.spyOn(liveDashboardApi, 'pruefeGatewayPreset').mockResolvedValue({ grund_erforderlich: true, felder: [frage] })
    const apply = vi.spyOn(liveDashboardApi, 'applyGatewayPreset').mockResolvedValue(
      { preset_id: 'evcc_ladepunkt', erstellt: 1, mappings: [], korrektur: [] })
    const { container } = render(<MemoryRouter><DatenquellenZuordnung /></MemoryRouter>)
    fireEvent.click(await screen.findByText(/alle aufklappen/))
    await waitFor(() => expect(container.querySelector('[data-preset-knopf="4"]')).not.toBeNull())
    fireEvent.click(container.querySelector('[data-preset-knopf="4"]') as HTMLElement)
    const dialog = await waitFor(() => document.querySelector('[data-preset-dialog]') as HTMLElement)
    fireEvent.click(dialog.querySelector('[data-preset-anwenden]') as HTMLElement)
    await waitFor(() => expect(document.querySelector('[data-sensorwechsel-feld="inv:4:ladung_kwh"]')).not.toBeNull())
    expect(apply).not.toHaveBeenCalled()
    fireEvent.click(document.querySelector('input[type="radio"][value="fortsetzung"]') as HTMLElement)
    fireEvent.click(document.querySelector('[data-sensorwechsel-ok]') as HTMLElement)
    await waitFor(() => expect(apply).toHaveBeenCalledWith({ preset_id: 'evcc_ladepunkt', anlage_id: 1, variablen: {},
      investition_id: 4, gruende: { 'inv:4:ladung_kwh': { grund: 'fortsetzung' } } }))
  })

  it('Sensorwechsel 3b-K (Mutanten F13, F18): der Dialog fragt nur die fragepflichtigen Felder; die Läufe der Antwort zeigen ihren Fortschritt', async () => {
    const frage = {
      grund_erforderlich: true, erster_wert: null, tage: 649, stand_alt: 1.0, stand_neu: null,
      sensor_key: 'inv:4:ladung_kwh', label: 'Ladung', verzeichnet: true, korrektur: null,
    }
    const ohneFrage = { ...frage, grund_erforderlich: false, sensor_key: 'inv:4:ladung_pv_kwh', label: 'Ladung PV' }
    vi.spyOn(liveDashboardApi, 'pruefeGatewayPreset').mockResolvedValue({ grund_erforderlich: true, felder: [frage, ohneFrage] })
    vi.spyOn(liveDashboardApi, 'applyGatewayPreset').mockResolvedValue({ preset_id: 'evcc_ladepunkt', erstellt: 1,
      mappings: [], korrektur: [{ lauf: 'L7', sensor_key: 'inv:4:ladung_kwh', label: 'Ladung', tage_neu: 9,
        zaehlerstaende_geloescht: 3 }] })
    const { container } = render(<MemoryRouter><DatenquellenZuordnung /></MemoryRouter>)
    fireEvent.click(await screen.findByText(/alle aufklappen/))
    await waitFor(() => expect(container.querySelector('[data-preset-knopf="4"]')).not.toBeNull())
    fireEvent.click(container.querySelector('[data-preset-knopf="4"]') as HTMLElement)
    const dialog = await waitFor(() => document.querySelector('[data-preset-dialog]') as HTMLElement)
    fireEvent.click(dialog.querySelector('[data-preset-anwenden]') as HTMLElement)
    await waitFor(() => expect(document.querySelector('[data-sensorwechsel-feld="inv:4:ladung_kwh"]')).not.toBeNull())
    expect(document.querySelector('[data-sensorwechsel-feld="inv:4:ladung_pv_kwh"]')).toBeNull()
    fireEvent.click(document.querySelector('input[type="radio"][value="fortsetzung"]') as HTMLElement)
    fireEvent.click(document.querySelector('[data-sensorwechsel-ok]') as HTMLElement)
    expect(await screen.findByText('Tage werden im Hintergrund neu gebildet: 2 von 9.')).toBeInTheDocument()
    expect(datenquellenApi.korrekturLauf).toHaveBeenCalledWith(1, 'L7')
  })

  it('Filter und Vorschau sind reine Auswahl/Formatierung', () => {
    expect(presetsFuerTyp(PRESETS, 'wallbox').map((p) => p.id)).toEqual(['evcc_ladepunkt'])
    expect(presetsFuerTyp(PRESETS, 'waermepumpe')).toEqual([])
    expect(presetsFuerAnlage(PRESETS).map((p) => p.id)).toEqual(['opendtu'])
    expect(topicVorschau('{prefix}/loadpoints/{loadpoint}/x', PRESETS[0], { loadpoint: '2' })).toBe('evcc/loadpoints/2/x')
  })
})
