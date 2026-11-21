/**
 * Sensorwechsel mit Grund (Sitzung 4) — der Einstieg «Zähler getauscht» ohne Rückweg und die Texte beim Wechsel.
 *
 * «Grund nachtragen» an einem verzeichneten Wechsel (`?nachtrag=<id>`, Befund «Zuordnung geändert, Grund fehlt») ist seit
 * Weg B entfernt (Sitzung B2); seine Tests sind mit ihm gegangen. Geblieben: (1) beim Wechsel genau «bleiben» und «löschen»,
 * kein «verwerfen»; (2) der Einstieg «Zähler getauscht» sagt vor dem Eintragen, dass sich ein Eintrag nicht zurücknehmen lässt
 * (Bauplan §12 Nr. 62).
 *
 * Schwesterdateien: SensorwechselDialog.test.tsx (Abfrage beim Wechsel, Fortschritt, Einstieg), SensorwechselStueck.test.tsx.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import SensorwechselDialog, { GRUND_FORTSETZUNG_FOLGE, GRUND_KORREKTUR, GRUND_LOESCHEN_FOLGE } from './SensorwechselDialog'
import ZaehlerGetauschtDialog, { ZG_ENDGUELTIG } from './ZaehlerGetauschtDialog'
import { datenquellenApi, type QuellePruefung } from '../../api/datenquellen'

const FRAGE: QuellePruefung = {
  grund_erforderlich: true, erster_wert: '2024-11-01T03:00:00', tage: 681, stand_alt: null, stand_neu: null,
  sensor_key: 'inv:2:ladung_kwh', label: 'SMA eCharger 22 – Ladung gesamt (kWh)', verzeichnet: true, korrektur: null,
}

vi.mock('../../api/datenquellen', () => ({
  datenquellenApi: {
    pruefeZaehlerGetauscht: vi.fn(),
    zaehlerGetauscht: vi.fn(),
  },
}))

beforeEach(() => { vi.useFakeTimers({ now: new Date(2026, 10, 18, 12, 0), shouldAdvanceTime: true }) })
afterEach(() => { vi.useRealTimers() })

describe('Sensorwechsel — Texte beim Wechsel (Weg B)', () => {
  it('beim Wechsel «bleiben» und «löschen», kein «verwerfen»', () => {
    render(<SensorwechselDialog isOpen fragen={[FRAGE]} onBestaetigen={vi.fn()} onAbbrechen={vi.fn()} />)
    expect(screen.getByText(GRUND_LOESCHEN_FOLGE)).toBeInTheDocument()
    expect(document.body.textContent).not.toContain(GRUND_KORREKTUR)
    expect(screen.getByText(GRUND_FORTSETZUNG_FOLGE)).toBeInTheDocument()
  })
})

describe('Sensorwechsel S4 — Einstieg ohne Rückweg (§12 Nr. 62)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('vor dem Eintragen steht der Satz; ohne «Eintragen» nicht', async () => {
    vi.mocked(datenquellenApi.pruefeZaehlerGetauscht).mockResolvedValue({
      weg: 'fortsetzung', sensor_key: 'inv:2:ladung_kwh', saetze: ['eedc überbrückt den Tausch.'], eintragen: true,
      getauscht_am: '2026-11-17T09:15:00' })
    const { unmount } = render(<ZaehlerGetauschtDialog anlageId={1} feldId="x" feldLabel="PV" onClose={() => {}} />)
    expect(await screen.findByText(ZG_ENDGUELTIG)).toBeInTheDocument()
    unmount()
    vi.mocked(datenquellenApi.pruefeZaehlerGetauscht).mockResolvedValue({
      weg: 'home_assistant', sensor_key: 'inv:2:ladung_kwh', saetze: ['In Home Assistant anpassen.'], eintragen: false,
      getauscht_am: null })
    render(<ZaehlerGetauschtDialog anlageId={1} feldId="x" feldLabel="PV" onClose={() => {}} />)
    expect(await screen.findByText('In Home Assistant anpassen.')).toBeInTheDocument()
    expect(screen.queryByText(ZG_ENDGUELTIG)).toBeNull()
  })
})
