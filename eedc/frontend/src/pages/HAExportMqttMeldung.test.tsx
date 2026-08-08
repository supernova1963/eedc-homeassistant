/**
 * MQTT-Export: ein Fehlschlag darf nicht wie ein Erfolg aussehen (T89667 #112).
 *
 * Phir0n meldete am 07.08.2026: Broker verbunden, Auto-Publish an — und die
 * Fläche zeigt „0 von 0 Sensoren publiziert" mit grünem Häkchen, während
 * „Verfügbare Sensoren (0)" darunter leer bleibt. Am Code gemessen war das
 * KEIN Bedienfehler:
 *
 *  1. `calculate_anlage_sensors` (Backend) hat in 712 Zeilen genau zwei
 *     Rückgaben — die leere greift, wenn die Anlage keine einzige Monatszeile
 *     hat. Der gesamte Export hängt an abgeschlossenen Monaten.
 *  2. Die Route sagt das auch: HTTP 404 „Keine Monatsdaten vorhanden".
 *  3. **Der Client verschluckte die Antwort.** Der `catch`-Zweig baute daraus
 *     ein ergebnisförmiges Objekt (`total: 0, success: 0`), der Grund landete
 *     in `message` — und die Anzeige rendert `message` nie, dafür ein fest
 *     verdrahtetes grünes `CheckCircle`.
 *
 * Diese Datei deckt Punkt 3 und den Leertext ab. Beides war ungeprüft: für
 * `HAExportSettingsTeile.tsx` gab es vor dem 08.08.2026 keine einzige Probe
 * (baumweit gegengesucht).
 *
 * Rot gegen HEAD~1 verifiziert — jede der drei Zusicherungen einzeln.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, waitFor, fireEvent } from '@testing-library/react'

const publishMqtt = vi.fn()
const getAnlageSensors = vi.fn()

vi.mock('../api', () => ({
  haApi: {
    getExportSensors: () => Promise.resolve({
      anlagen: [], investitionen: [], sensor_count: 0, mqtt_available: true,
    }),
    getMqttConfig: () => Promise.resolve({
      host: 'core-mosquitto', port: 1883, username: 'mqtt_pv',
      auto_publish: true, quelle: 'addon',
    }),
    getAnlageSensors: (id: number) => getAnlageSensors(id),
    getYamlSnippet: () => Promise.resolve({ yaml: '', sensor_count: 0 }),
    publishMqtt: (id: number) => publishMqtt(id),
    testMqttConnection: () => Promise.resolve({ connected: true, broker: 'core-mosquitto:1883' }),
    setAutoPublish: () => Promise.resolve({ gespeichert: true, enabled: true }),
  },
  anlagenApi: { update: () => Promise.resolve({}) },
}))

vi.mock('../api/datenquellen', () => ({ VERBINDUNG_GEAENDERT_EVENT: 'verbindung-geaendert' }))

import { MqttExportVerwaltung } from './HAExportSettingsTeile'

const LEERE_ANLAGE = { anlage_id: 1, anlage_name: 'Phir0ns Anlage', sensors: [] }

beforeEach(() => {
  publishMqtt.mockReset()
  getAnlageSensors.mockReset()
  getAnlageSensors.mockResolvedValue(LEERE_ANLAGE)
})
afterEach(cleanup)

async function rendereUndPubliziere() {
  render(<MqttExportVerwaltung anlageId={1} />)
  // Auf die geladene Fläche warten, sonst klickt der Test ins Skelett.
  const knopf = await screen.findByRole('button', { name: /Sensoren publizieren/i })
  fireEvent.click(knopf)
}

describe('MQTT-Export: gescheiterter Publish', () => {
  // Bewusst zwei Proben statt einer mit zwei Zusicherungen: reißt die erste
  // Assertion, sind die folgenden nicht belegt — und genau diese beiden Sätze
  // sind der Kern des Fundes.
  it('nennt den Grund der API', async () => {
    // Genau die Antwort, die Phir0ns Anlage erzeugt: 404 mit Grund.
    publishMqtt.mockRejectedValue(new Error('Keine Monatsdaten vorhanden'))

    await rendereUndPubliziere()

    await waitFor(() => {
      expect(screen.getByText('Keine Monatsdaten vorhanden')).toBeInTheDocument()
    })
  })

  it('zeigt dabei nicht mehr „0 von 0 Sensoren publiziert"', async () => {
    publishMqtt.mockRejectedValue(new Error('Keine Monatsdaten vorhanden'))

    await rendereUndPubliziere()

    // Erst abwarten, dass die Meldung überhaupt gerendert ist — sonst wäre
    // die Abwesenheit trivial erfüllt, weil noch gar nichts dasteht.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Sensoren publizieren/i })).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.queryByText(/von .* Sensoren publiziert/)).not.toBeInTheDocument()
    })
  })

  it('meldet einen echten Erfolg weiterhin als Zahl', async () => {
    // Gegenprobe: der Erfolgsfall darf durch den Fehlerzweig nicht verlieren.
    publishMqtt.mockResolvedValue({
      message: 'ok', anlage_id: 1, total: 36, success: 36, failed: 0,
    })

    await rendereUndPubliziere()

    await waitFor(() => {
      expect(screen.getByText(/36 von 36 Sensoren publiziert/)).toBeInTheDocument()
    })
  })
})

describe('MQTT-Export: leere Sensorliste', () => {
  it('erklärt, dass der Export abgeschlossene Monatsdaten braucht', async () => {
    render(<MqttExportVerwaltung anlageId={1} />)

    await waitFor(() => {
      expect(screen.getByText('Noch keine Sensoren zu exportieren')).toBeInTheDocument()
    })
    expect(screen.getByText(/abgeschlossenen Monatsdaten/)).toBeInTheDocument()
  })

  it('schweigt, sobald Sensoren da sind', async () => {
    getAnlageSensors.mockResolvedValue({
      anlage_id: 1,
      anlage_name: 'Winterborn',
      sensors: [{
        key: 'pv_erzeugung', name: 'PV-Erzeugung', value: 412.5, unit: 'kWh',
        icon: 'mdi:solar-power', category: 'energie',
      }],
    })

    render(<MqttExportVerwaltung anlageId={1} />)

    await waitFor(() => {
      expect(screen.getByText(/Verfügbare Sensoren \(1\)/)).toBeInTheDocument()
    })
    expect(screen.queryByText('Noch keine Sensoren zu exportieren')).not.toBeInTheDocument()
  })
})
