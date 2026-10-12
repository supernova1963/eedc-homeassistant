/**
 * N-739 (b): ein nicht erfasstes Netzfeld wird im Monatsformular nicht mit 0 vorbelegt.
 *
 * Die Spalten `einspeisung_kwh`/`netzbezug_kwh` sind NOT NULL; eine Zeile, die ein Import ohne Netzfelder anlegte,
 * steht mit 0 da, ohne dass jemand eine 0 geliefert hat (N-734: «nicht erfasst»). Das Formular belegte diese 0 vor —
 * wer dem Checker folgte und ungeprüft speicherte, stempelte sie als eingetragen (`manual:form`): Cockpit zeigte
 * wieder 0 / 0 / 100 %, der Checker schwieg, und der HA-Statistik-Import kam danach auch mit Haken nicht mehr durch.
 *
 * Jetzt: `einspeisung_erfasst/netzbezug_erfasst === false` (MonatsdatenResponse) ⇒ das Feld startet leer; der beste
 * Vorschlag (hier HA-Statistik) füllt es wie jedes leere Feld. Ein erfasster Wert — auch 0 — bleibt stehen.
 * Schwester: `monatsdaten-ha-vorbelegung-n534.test.tsx` (dieselbe Bauform).
 */
import { describe, expect, it, vi } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { gespeicherterNetzwert } from '../lib/erfassungZustand'

const zustand: { status: unknown } = { status: null }

vi.mock('../hooks', () => ({
  useInvestitionen: () => ({ investitionen: [], loading: false }),
  useAktuellerStrompreis: () => ({ strompreis: null }),
}))

vi.mock('../api', () => ({
  wetterApi: { getMonatsdaten: () => Promise.reject(new Error('kein Wetter im Test')) },
  monatsabschlussApi: {
    getStatus: () => (zustand.status ? Promise.resolve(zustand.status) : Promise.reject(new Error('kein Status'))),
  },
  investitionenApi: { getMonatsdatenByMonth: () => Promise.resolve([]) },
}))

const MonatsdatenForm = (await import('../components/forms/MonatsdatenForm')).default

const feld = (name: string) => document.querySelector(`input[name="${name}"]`) as HTMLInputElement | null

// Die Zeile eines Wallbox-Imports: 0 / 0 ohne Herkunft.
const nichtErfasst = {
  id: 9, anlage_id: 1, jahr: 2025, monat: 7, einspeisung_kwh: 0, netzbezug_kwh: 0,
  einspeisung_erfasst: false, netzbezug_erfasst: false,
}

const feldStatus = (name: string, label: string, vorschlag?: number) => ({
  feld: name, label, einheit: 'kWh', aktueller_wert: null, quelle: null,
  vorschlaege: vorschlag === undefined ? [] : [
    { wert: vorschlag, quelle: 'ha_statistics', konfidenz: 92, beschreibung: 'Aus HA-Statistik (Recorder-DB)' },
  ],
  warnungen: [], strategie: 'sensor', sensor_id: `sensor.${name}`, typ: 'number', gruppe: 'zaehler',
})

const status = (es?: number, nb?: number) => ({
  anlage_id: 1, anlage_name: 'Test', jahr: 2025, monat: 7, ist_abgeschlossen: true,
  ha_mapping_konfiguriert: true, connector_konfiguriert: false, cloud_import_konfiguriert: false,
  mqtt_inbound_konfiguriert: false, portal_import_vorhanden: true, datenquelle: 'portal_import',
  basis_felder: [feldStatus('einspeisung_kwh', 'Einspeisung', es), feldStatus('netzbezug_kwh', 'Netzbezug', nb)],
  optionale_felder: [], investitionen: [],
})

function oeffne(monatsdaten: Record<string, unknown>) {
  render(
    <MonatsdatenForm anlageId={1} onSubmit={() => Promise.resolve()} onCancel={() => {}} monatsdaten={monatsdaten as never} />,
  )
}

describe('Netzfeld nicht erfasst (N-739 b)', () => {
  it('ohne Status: beide Felder starten leer statt mit 0', async () => {
    zustand.status = null
    oeffne(nichtErfasst)
    await waitFor(() => expect(feld('einspeisung_kwh')).not.toBeNull())
    expect(feld('einspeisung_kwh')!.value).toBe('')
    expect(feld('netzbezug_kwh')!.value).toBe('')
  })

  it('mit HA-Vorschlag: das leere Feld bekommt den Vorschlag (700 / 250), nicht die 0', async () => {
    zustand.status = status(700, 250)
    oeffne(nichtErfasst)
    await waitFor(() => expect(feld('einspeisung_kwh')!.value).toBe('700'))
    expect(feld('netzbezug_kwh')!.value).toBe('250')
  })

  it('Gegenprobe: eine erfasste 0 bleibt als 0 stehen', async () => {
    zustand.status = status(700, 250)
    oeffne({ ...nichtErfasst, einspeisung_erfasst: true, netzbezug_erfasst: true })
    await waitFor(() => expect(feld('einspeisung_kwh')).not.toBeNull())
    expect(feld('einspeisung_kwh')!.value).toBe('0')
    expect(feld('netzbezug_kwh')!.value).toBe('0')
  })

  it('der Helfer: ohne Marke (ältere Antwort) gilt der gespeicherte Wert wie bisher', () => {
    expect(gespeicherterNetzwert({ einspeisung_kwh: 0, netzbezug_kwh: 120 }, 'einspeisung_kwh')).toBe('0')
    expect(gespeicherterNetzwert({ einspeisung_kwh: 0, netzbezug_kwh: 120, netzbezug_erfasst: false }, 'netzbezug_kwh')).toBe('')
    expect(gespeicherterNetzwert(null, 'netzbezug_kwh')).toBe('')
  })
})
