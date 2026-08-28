/**
 * #400 — Sensor-Abwahl: Häkchen, Rückfrage, und wann NICHT gefragt wird.
 *
 * Zwei Melder in 24 Stunden (rapahl per PN, Knallfrosch T89667 #236): eedc
 * liefert alles nach Home Assistant, und dort lässt es sich nicht dauerhaft
 * loswerden — der Registry-Eintrag bleibt, bei der nächsten Discovery kommt der
 * Sensor wieder. Die Abwahl muss auf der **sendenden** Seite sitzen.
 *
 * **Entscheid Gernot (28.08.):** Alle Sensoren bleiben per Default an; abgewählt
 * wird bewusst, und vor dem Wirksamwerden fragt eedc nach und nennt den Verlust.
 *
 * ⭐ **Die zweite Hälfte ist so wichtig wie die erste:** Wer nur wieder ANWÄHLT,
 * verliert nichts — und darf deshalb nicht gefragt werden. Eine Rückfrage, die
 * auch bei harmlosen Änderungen kommt, wird weggeklickt, und dann schützt sie
 * bei der gefährlichen auch nicht mehr.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const setSensorAbwahl = vi.fn()
const getSensorAbwahl = vi.fn()

const SENSOREN = [
  { key: 'pv_erzeugung_gesamt_kwh', name: 'PV Erzeugung Gesamt', unit: 'kWh', icon: 'mdi:solar-power', category: 'energie', formel: 'Σ', exportiert: true },
  { key: 'einspeisung_gesamt_kwh', name: 'Einspeisung Gesamt', unit: 'kWh', icon: 'mdi:transmission-tower', category: 'energie', formel: 'Σ', exportiert: true },
  { key: 'roi_prozent', name: 'ROI', unit: '%', icon: 'mdi:percent', category: 'investition', formel: 'x', exportiert: true },
]

const ANLAGE = {
  anlage_id: 1,
  anlage_name: 'Testanlage',
  sensors: SENSOREN.map(s => ({
    key: s.key, name: s.name, value: 42, unit: s.unit, icon: s.icon,
    category: s.category, formel: s.formel, berechnung: null,
    device_class: null, state_class: null,
  })),
}

vi.mock('../api', () => ({
  haApi: {
    getExportSensors: () => Promise.resolve({
      anlagen: [], investitionen: [], sensor_count: 3, mqtt_available: true,
    }),
    getMqttConfig: () => Promise.resolve({
      host: 'core-mosquitto', port: 1883, username: '', auto_publish: true, quelle: 'addon',
    }),
    getAnlageSensors: () => Promise.resolve(ANLAGE),
    getYamlSnippet: () => Promise.resolve({ yaml: '', sensor_count: 3 }),
    publishMqtt: () => Promise.resolve({ total: 3, success: 3, failed: 0 }),
    removeMqtt: () => Promise.resolve(),
    testMqttConnection: () => Promise.resolve({ connected: true, broker: 'x' }),
    setAutoPublish: () => Promise.resolve({ gespeichert: true, enabled: true }),
    getSensorAbwahl: () => getSensorAbwahl(),
    setSensorAbwahl: (keys: string[]) => setSensorAbwahl(keys),
  },
  anlagenApi: { update: () => Promise.resolve({}) },
}))

vi.mock('../api/datenquellen', () => ({ VERBINDUNG_GEAENDERT_EVENT: 'verbindung-geaendert' }))

import { MqttExportVerwaltung } from './HAExportSettingsTeile'

beforeEach(() => {
  setSensorAbwahl.mockReset()
  getSensorAbwahl.mockReset()
  getSensorAbwahl.mockResolvedValue({ abgewaehlt: [], sensoren: SENSOREN })
  setSensorAbwahl.mockResolvedValue({
    gespeichert: true, abgewaehlt: ['einspeisung_gesamt_kwh'],
    neu_abgewaehlt: ['einspeisung_gesamt_kwh'], entfernte_topics: 3, fehler: null,
  })
})
afterEach(cleanup)

async function haekchen(name: RegExp) {
  return await screen.findByRole('checkbox', { name })
}

describe('#400 Sensor-Abwahl', () => {
  it('speichert NICHT, solange die Rückfrage nicht bestätigt ist', async () => {
    render(<MqttExportVerwaltung anlageId={1} />)

    fireEvent.click(await haekchen(/Einspeisung Gesamt nach Home Assistant exportieren/i))
    fireEvent.click(await screen.findByRole('button', { name: /Auswahl speichern/i }))

    // Die Rückfrage steht — und sie nennt den Verlust beim Namen.
    expect(await screen.findByText(/Sensoren abwählen\?/i)).toBeInTheDocument()
    expect(
      screen.getByText(/Daten in Home Assistant und auf dem MQTT-Broker sind\s+damit verloren/i)
    ).toBeInTheDocument()
    expect(setSensorAbwahl).not.toHaveBeenCalled()
  })

  it('schickt nach der Bestätigung genau den abgewählten Schlüssel', async () => {
    render(<MqttExportVerwaltung anlageId={1} />)

    fireEvent.click(await haekchen(/Einspeisung Gesamt nach Home Assistant exportieren/i))
    fireEvent.click(await screen.findByRole('button', { name: /Auswahl speichern/i }))
    fireEvent.click(await screen.findByRole('button', { name: /Abwählen und entfernen/i }))

    await waitFor(() => expect(setSensorAbwahl).toHaveBeenCalledWith(['einspeisung_gesamt_kwh']))
  })

  it('fragt NICHT nach, wenn nur wieder angewählt wird — dabei geht nichts verloren', async () => {
    getSensorAbwahl.mockResolvedValue({
      abgewaehlt: ['einspeisung_gesamt_kwh'],
      sensoren: SENSOREN.map(s =>
        s.key === 'einspeisung_gesamt_kwh' ? { ...s, exportiert: false } : s),
    })
    setSensorAbwahl.mockResolvedValue({
      gespeichert: true, abgewaehlt: [], neu_abgewaehlt: [], entfernte_topics: 0, fehler: null,
    })

    render(<MqttExportVerwaltung anlageId={1} />)

    // Wieder anhaken = wieder exportieren
    fireEvent.click(await haekchen(/Einspeisung Gesamt nach Home Assistant exportieren/i))
    fireEvent.click(await screen.findByRole('button', { name: /Auswahl speichern/i }))

    await waitFor(() => expect(setSensorAbwahl).toHaveBeenCalledWith([]))
    expect(screen.queryByText(/Sensoren abwählen\?/i)).not.toBeInTheDocument()
  })

  it('das Sammel-Häkchen der Kategorie wählt die ganze Gruppe ab', async () => {
    render(<MqttExportVerwaltung anlageId={1} />)

    fireEvent.click(await haekchen(/Alle Sensoren der Kategorie Energie exportieren/i))
    fireEvent.click(await screen.findByRole('button', { name: /Auswahl speichern/i }))

    // Beide Energie-Sensoren stehen in der Rückfrage, der Investitions-Sensor
    // nicht — sonst hätte das Sammel-Häkchen über seine Kategorie hinausgegriffen.
    await screen.findByText(/Sensoren abwählen\?/i)
    // Die Aufzählung existiert nur in der Rückfrage — die Sensorliste selbst
    // rendert <div>, kein <li>.
    const genannt = screen.getAllByRole('listitem').map(li => li.textContent)
    expect(genannt).toEqual(['PV Erzeugung Gesamt', 'Einspeisung Gesamt'])
    expect(genannt).not.toContain('ROI')
  })

  it('„Alle Sensoren entfernen" fragt vorher nach', async () => {
    render(<MqttExportVerwaltung anlageId={1} />)

    fireEvent.click(await screen.findByRole('button', { name: /Sensoren entfernen/i }))

    expect(await screen.findByText(/Alle Sensoren entfernen\?/i)).toBeInTheDocument()
    expect(screen.getByText(/Deine Daten in eedc bleiben unberührt/i)).toBeInTheDocument()
  })
})
