/**
 * N-545 — Was mit dem Update dazukam: Hinweiskasten und „Neu"-Markierung.
 *
 * **Entscheid Gernot (22.09.2026).** Neue Sensor-Definitionen starten bei einer
 * BESTEHENDEN Installation abgewählt; eine Neuinstallation bekommt weiterhin
 * alles. Anlass ist v4.0.27: 21 neue Entitäten auf einen Schlag, zwei Melder
 * binnen 24 Stunden (#400), und in Home Assistant bleibt der Registry-Eintrag.
 * Rainer hat es für das nächste Paket direkt gesagt — er will vorher wissen,
 * was kommt.
 *
 * ⭐ **Die Fläche muss beides können, und beides ist hier geprüft:** sagen, dass
 * etwas dazugekommen ist (Kasten + Badge), und es mit einem Griff annehmen
 * („Alle neuen anwählen"). Das Annehmen darf **nicht** nachfragen: die
 * Rückfrage nennt den Verlust, und beim Anwählen geht nichts verloren (#400,
 * dieselbe Begründung wie dort — eine Rückfrage, die auch bei harmlosen
 * Änderungen kommt, wird weggeklickt).
 *
 * ⚠ **Und der Kasten muss schweigen können.** Ein älteres Backend liefert weder
 * `neu` noch `neues_paket`; eine Neuinstallation liefert sie, hat aber nichts
 * abgewählt. In beiden Fällen wäre der Kasten eine Meldung über nichts.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const setSensorAbwahl = vi.fn()
const getSensorAbwahl = vi.fn()

/** Die drei Schlüssel, die in dieser Probe „Paket 1" sind. */
const PAKET_KEYS = [
  'eedc_ueberschuss_heute_kwh',
  'eedc_speicher_soc_prozent',
  'sonstiges_verbrauch_monat_kwh',
]

const SENSOREN = [
  { key: 'pv_erzeugung_gesamt_kwh', name: 'PV Erzeugung Gesamt', unit: 'kWh', icon: 'mdi:solar-power', category: 'energie', formel: 'Σ', exportiert: true, neu: false },
  { key: 'roi_prozent', name: 'ROI', unit: '%', icon: 'mdi:percent', category: 'investition', formel: 'x', exportiert: true, neu: false },
  { key: 'eedc_ueberschuss_heute_kwh', name: 'Überschuss heute', unit: 'kWh', icon: 'mdi:solar-power-variant', category: 'steuerung', formel: 'Σ', exportiert: false, neu: true },
  { key: 'eedc_speicher_soc_prozent', name: 'Speicher-Ladestand', unit: '%', icon: 'mdi:home-battery', category: 'steuerung', formel: 'Σ', exportiert: false, neu: true },
  { key: 'sonstiges_verbrauch_monat_kwh', name: 'Verbrauch (Monat)', unit: 'kWh', icon: 'mdi:power-plug', category: 'sonstiges', formel: 'Σ', exportiert: false, neu: true },
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

const PAKET_INFO = {
  paket: 1,
  label: 'eedc@ha, Teil 1 — Steuerungshilfen, Preise und Speicher',
  keys: PAKET_KEYS,
  abgewaehlt: PAKET_KEYS,
}

vi.mock('../api', () => ({
  haApi: {
    getExportSensors: () => Promise.resolve({
      anlagen: [], investitionen: [], sensor_count: 5, mqtt_available: true,
    }),
    getMqttConfig: () => Promise.resolve({
      host: 'core-mosquitto', port: 1883, username: '', auto_publish: true, quelle: 'addon',
    }),
    getAnlageSensors: () => Promise.resolve(ANLAGE),
    getYamlSnippet: () => Promise.resolve({ yaml: '', sensor_count: 5 }),
    publishMqtt: () => Promise.resolve({ total: 5, success: 5, failed: 0 }),
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

/** Der Bestandsfall: die drei Paket-Schlüssel stehen abgewählt da. */
function bestandNachUpdate() {
  getSensorAbwahl.mockResolvedValue({
    abgewaehlt: [...PAKET_KEYS].sort(),
    sensoren: SENSOREN,
    neues_paket: PAKET_INFO,
  })
}

beforeEach(() => {
  setSensorAbwahl.mockReset()
  getSensorAbwahl.mockReset()
  bestandNachUpdate()
  setSensorAbwahl.mockResolvedValue({
    gespeichert: true, abgewaehlt: [], neu_abgewaehlt: [], entfernte_topics: 0, fehler: null,
  })
})
afterEach(cleanup)

describe('N-545 — der Hinweis über der Liste', () => {
  it('nennt Anzahl, Label und wie viele noch abgewählt sind', async () => {
    render(<MqttExportVerwaltung anlageId={1} />)

    expect(
      await screen.findByText(/Mit dem letzten Update kamen 3 Sensoren dazu/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/eedc@ha, Teil 1/)).toBeInTheDocument()
    expect(
      screen.getByText(/starten sie abgewählt — 3 davon sind es noch/i)
    ).toBeInTheDocument()
  })

  it('schweigt bei einer Neuinstallation — dort ist nichts abgewählt', async () => {
    getSensorAbwahl.mockResolvedValue({
      abgewaehlt: [],
      sensoren: SENSOREN.map(s => ({ ...s, exportiert: true })),
      neues_paket: { ...PAKET_INFO, abgewaehlt: [] },
    })

    render(<MqttExportVerwaltung anlageId={1} />)

    await screen.findByText('Steuerungshilfen')   // die Fläche steht
    expect(screen.queryByText(/Mit dem letzten Update kamen/i)).not.toBeInTheDocument()
    // ⭐ Die Badges bleiben trotzdem — „neu" ist eine Eigenschaft der
    // Definition, nicht des Abwahl-Zustands.
    fireEvent.click(await screen.findByRole('button', { name: /Steuerungshilfen/i }))
    expect((await screen.findAllByText('Neu')).length).toBeGreaterThan(0)
  })

  it('schweigt ganz bei einem älteren Backend ohne die Felder', async () => {
    getSensorAbwahl.mockResolvedValue({
      abgewaehlt: [],
      sensoren: SENSOREN.map(({ neu: _neu, ...rest }) => ({ ...rest, exportiert: true })),
    })

    render(<MqttExportVerwaltung anlageId={1} />)

    await screen.findByText('Steuerungshilfen')
    expect(screen.queryByText(/Mit dem letzten Update kamen/i)).not.toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: /Steuerungshilfen/i }))
    await screen.findByText('Überschuss heute')
    expect(screen.queryByText('Neu')).not.toBeInTheDocument()
  })
})

describe('N-545 — die Markierung an der Zeile', () => {
  it('trägt „Neu" genau an den Paket-Sensoren', async () => {
    render(<MqttExportVerwaltung anlageId={1} />)

    // Die Gruppe „Steuerungshilfen" ist zugeklappt — erst aufklappen.
    fireEvent.click(await screen.findByRole('button', { name: /Steuerungshilfen/i }))
    await screen.findByText('Überschuss heute')
    expect(screen.getAllByText('Neu')).toHaveLength(2)

    // ⛔ Gegenprobe: der Bestands-Sensor in der offenen Gruppe „Energie" trägt
    // sie NICHT — sonst hinge das Badge an der Zeile statt am Paket.
    const bestand = screen.getByText('PV Erzeugung Gesamt').closest('div')
    expect(bestand?.textContent).not.toContain('Neu')
  })
})

describe('N-545 — „Alle neuen anwählen"', () => {
  it('füllt nur den Entwurf und speichert noch nicht', async () => {
    render(<MqttExportVerwaltung anlageId={1} />)

    fireEvent.click(await screen.findByRole('button', { name: /Alle neuen anwählen/i }))

    // Der Entwurf ist leer — der Änderungsbalken sagt es, gespeichert ist nichts.
    expect(await screen.findByText(/0 Sensoren abgewählt/i)).toBeInTheDocument()
    expect(setSensorAbwahl).not.toHaveBeenCalled()
  })

  it('speichert ohne Rückfrage — beim Anwählen geht nichts verloren', async () => {
    render(<MqttExportVerwaltung anlageId={1} />)

    fireEvent.click(await screen.findByRole('button', { name: /Alle neuen anwählen/i }))
    fireEvent.click(await screen.findByRole('button', { name: /Auswahl speichern/i }))

    await waitFor(() => expect(setSensorAbwahl).toHaveBeenCalledWith([]))
    expect(screen.queryByText(/Sensoren abwählen\?/i)).not.toBeInTheDocument()
  })

  it('bleibt sichtbar, solange der Server-Zustand sie abgewählt führt', async () => {
    render(<MqttExportVerwaltung anlageId={1} />)

    fireEvent.click(await screen.findByRole('button', { name: /Alle neuen anwählen/i }))

    // ⛔ Der Kasten haengt am SERVER-Zustand. Verschwände er beim letzten
    // Häkchen, wäre mitten in der Arbeit auch der Weg zurück weg.
    expect(await screen.findByText(/Mit dem letzten Update kamen 3 Sensoren dazu/i)).toBeInTheDocument()
    expect(screen.getByText(/keiner davon ist es noch/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Alle neuen anwählen/i })).not.toBeInTheDocument()
  })
})
